from __future__ import annotations

import json
import os
import re
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence

from app.evidence.ledger import EvidenceLedger
from app.evidence.models import Claim, ClaimVerdict, Evidence, EvidenceStatus

from .models import (
    AdaptiveDebateConfig,
    DebateResponse,
    JudgeClaimInput,
    JudgeEvaluation,
    JudgeEvidenceInput,
    JudgeRequest,
    JudgeVerdict,
    RoutingDecision,
)


class JudgeProvider(ABC):
    mode = "unknown"

    @abstractmethod
    def evaluate(self, claim: JudgeClaimInput, evidence: Sequence[JudgeEvidenceInput], config: AdaptiveDebateConfig, round_number: int, retry_count: int) -> JudgeEvaluation:
        raise NotImplementedError


def _routing(verdict: JudgeVerdict) -> RoutingDecision:
    return {
        JudgeVerdict.SUPPORTED: RoutingDecision.APPROVED,
        JudgeVerdict.PARTIALLY_SUPPORTED: RoutingDecision.MORE_EVIDENCE_REQUIRED,
        JudgeVerdict.CONTRADICTED: RoutingDecision.ESCALATE_TO_JUDGE,
        JudgeVerdict.AMBIGUOUS: RoutingDecision.ESCALATE_TO_JUDGE,
        JudgeVerdict.STALE_EVIDENCE: RoutingDecision.MORE_EVIDENCE_REQUIRED,
        JudgeVerdict.SOURCE_QUALITY_INSUFFICIENT: RoutingDecision.MORE_EVIDENCE_REQUIRED,
        JudgeVerdict.UNVERIFIABLE: RoutingDecision.UNVERIFIABLE,
    }[verdict]


class DeterministicJudge(JudgeProvider):
    mode = "deterministic_mock"

    def evaluate(self, claim, evidence, config, round_number, retry_count):
        referenced = {item.evidence_id: item for item in evidence if item.evidence_id in claim.evidence_ids}
        missing_ids = [item for item in claim.evidence_ids if item not in referenced]
        if claim.external_verification_required and not claim.evidence_ids:
            return self._result(claim, JudgeVerdict.UNVERIFIABLE, [], [], 0.0, 0.0, "External claim has no supplied evidence", round_number, retry_count)
        if missing_ids:
            return self._result(claim, JudgeVerdict.UNVERIFIABLE, [], [], 0.0, 0.0, "Referenced evidence is missing from supplied evidence", round_number, retry_count)
        if not referenced:
            return self._result(claim, JudgeVerdict.UNVERIFIABLE, [], [], 0.0, 0.0, "No evidence was supplied for this claim", round_number, retry_count)

        contradiction = [item.evidence_id for item in referenced.values() if item.support_status == "CONTRADICTS" or item.verification_status == "CONTRADICTS"]
        support = [item.evidence_id for item in referenced.values() if item.support_status == "SUPPORTS" or item.verification_status == "SUPPORTS"]
        quality = min(item.source_quality_score for item in referenced.values())
        freshness = min(item.freshness_score for item in referenced.values())
        if contradiction and support:
            verdict = JudgeVerdict.AMBIGUOUS
            reason = "Supplied evidence contains both supporting and contradicting records"
        elif contradiction:
            verdict = JudgeVerdict.CONTRADICTED
            reason = "Supplied evidence explicitly contradicts the claim"
        elif quality < config.minimum_source_quality:
            verdict = JudgeVerdict.SOURCE_QUALITY_INSUFFICIENT
            reason = "The lowest supplied source quality is below policy threshold"
        elif freshness < config.minimum_freshness:
            verdict = JudgeVerdict.STALE_EVIDENCE
            reason = "The lowest supplied evidence freshness is below policy threshold"
        elif support and len(support) == len(referenced):
            verdict = JudgeVerdict.SUPPORTED
            reason = "Every supplied evidence record explicitly supports the claim"
        elif support:
            verdict = JudgeVerdict.PARTIALLY_SUPPORTED
            reason = "Only part of the supplied evidence explicitly supports the claim"
        else:
            verdict = JudgeVerdict.UNVERIFIABLE
            reason = "Supplied evidence has no explicit support verdict"
        return self._result(claim, verdict, support, contradiction, quality, freshness, reason, round_number, retry_count)

    def _result(self, claim, verdict, support, contradiction, quality, freshness, reason, round_number, retry_count):
        used = list(dict.fromkeys([*support, *contradiction]))
        return JudgeEvaluation(
            claim_id=claim.claim_id,
            verdict=verdict,
            evidence_used_ids=used,
            contradicting_evidence_ids=contradiction,
            evidence_status="CONTRADICTED" if contradiction else "SUPPORTED" if support else "UNVERIFIABLE",
            source_quality=quality,
            freshness=freshness,
            confidence=round(min(1.0, (quality + freshness) / 2) if used else 0.0, 3),
            reason=reason,
            required_next_action=_routing(verdict),
            judge_mode=self.mode,
            debate_round=round_number,
            retry_count=retry_count,
        )


class OpenAIJudge(JudgeProvider):
    mode = "openai"

    def __init__(self, api_key: str, model: str, endpoint: str = "https://api.openai.com/v1/responses"):
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint

    def evaluate(self, claim, evidence, config, round_number, retry_count):
        allowed_evidence = [item.model_dump(mode="json") for item in evidence if item.evidence_id in claim.evidence_ids]
        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": "You are a conservative claim verifier. Use only the supplied claim and evidence. Do not use memory as evidence. Return JSON only. Do not provide hidden reasoning.",
                },
                {
                    "role": "user",
                    "content": json.dumps({
                        "claim": claim.model_dump(mode="json"),
                        "evidence": allowed_evidence,
                        "output_schema": {
                            "verdict": [item.value for item in JudgeVerdict],
                            "evidence_used_ids": ["string"],
                            "contradicting_evidence_ids": ["string"],
                            "evidence_status": "string",
                            "source_quality": 0.0,
                            "freshness": 0.0,
                            "confidence": 0.0,
                            "reason": "concise auditable reason",
                            "required_next_action": [item.value for item in RoutingDecision],
                        },
                    }, ensure_ascii=False),
                },
            ],
            "max_output_tokens": 700,
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = json.loads(response.read().decode("utf-8"))
        value = self._parse_response(raw)
        value["claim_id"] = claim.claim_id
        value["judge_mode"] = self.mode
        value["debate_round"] = round_number
        value["retry_count"] = retry_count
        evaluation = JudgeEvaluation.model_validate(value)
        allowed = set(claim.evidence_ids)
        if set(evaluation.evidence_used_ids) - allowed or set(evaluation.contradicting_evidence_ids) - allowed:
            raise ValueError("Judge returned an evidence ID not supplied with the claim")
        return evaluation

    @staticmethod
    def _parse_response(payload: Dict[str, Any]) -> Dict[str, Any]:
        text = payload.get("output_text", "")
        if not text:
            text = " ".join(
                content.get("text", "")
                for output in payload.get("output", [])
                for content in output.get("content", [])
                if isinstance(content, dict)
            )
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.S)
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.S)
            if not match:
                raise ValueError("Judge response was not JSON")
            value = json.loads(match.group(0))
        if not isinstance(value, dict):
            raise ValueError("Judge response must be an object")
        return value


class JudgeService:
    def __init__(self, provider: Optional[JudgeProvider] = None, fallback: Optional[JudgeProvider] = None):
        self.provider = provider or self._default_provider()
        self.fallback = fallback or DeterministicJudge()

    @staticmethod
    def _default_provider() -> JudgeProvider:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if api_key and os.getenv("JUDGE_MODE", "openai").lower() == "openai":
            return OpenAIJudge(api_key, os.getenv("OPENAI_MODEL", "gpt-5.6-luna"))
        return DeterministicJudge()

    def evaluate(self, claim: JudgeClaimInput, evidence: List[JudgeEvidenceInput], config: AdaptiveDebateConfig, round_number: int, retry_count: int) -> JudgeEvaluation:
        if not claim.evidence_ids and claim.external_verification_required:
            return self.fallback.evaluate(claim, evidence, config, round_number, retry_count)
        try:
            return self.provider.evaluate(claim, evidence, config, round_number, retry_count)
        except Exception:
            return self.fallback.evaluate(claim, evidence, config, round_number, retry_count)

    def debate(self, request: JudgeRequest) -> DebateResponse:
        config = AdaptiveDebateConfig(max_debate_rounds=request.max_debate_rounds, max_retries=request.max_retries)
        response = DebateResponse()
        for claim in request.claims:
            current = None
            retries = 0
            for round_number in range(1, config.max_debate_rounds + 1):
                current = self.evaluate(claim, request.evidence, config, round_number, retries)
                if current.required_next_action in {RoutingDecision.APPROVED, RoutingDecision.UNVERIFIABLE} or current.verdict == JudgeVerdict.CONTRADICTED:
                    break
                if retries >= config.max_retries:
                    current = current.model_copy(update={
                        "verdict": JudgeVerdict.UNVERIFIABLE,
                        "required_next_action": RoutingDecision.UNVERIFIABLE,
                        "reason": "Retry and debate limits were exhausted without resolving the claim",
                    })
                    response.warnings.append(f"Claim {claim.claim_id} became UNVERIFIABLE after bounded debate")
                    break
                retries += 1
            if current is not None:
                response.evaluations.append(current)
                response.routing[claim.claim_id] = current.required_next_action
                response.retry_counts[claim.claim_id] = retries
                response.debate_round = max(response.debate_round, current.debate_round)
        response.partial = bool(response.warnings)
        return response
