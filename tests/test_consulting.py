import unittest

from app.consulting.agent import ConsultingAgent
from app.consulting.models import ConsultingRequest
from app.metadata.models import MetadataItem, UserConfirmedMetadata
from app.retrieval.models import RetrievalRequest, SearchResult
from app.retrieval.pipeline import RetrievalPipeline
from app.retrieval.registry import SourcePolicy, SourceRegistry


class ConsultingProvider:
    def __init__(self, results):
        self.results = results

    def search(self, query, limit):
        return [item.model_copy(update={"query": query}) for item in self.results[:limit]]


class ConsultingFixtureTests(unittest.TestCase):
    def _agent(self, results):
        registry = SourceRegistry(
            sources=[SourcePolicy(name="fixture", publisher="Official Fixture", source_type="OFFICIAL_COMPANY")]
        )

        def fetcher(url):
            company = "Alpha" if "alpha" in url else "Beta"
            return 200, "text/html", (
                f"Published: 2026-07-01. Application deadline: 2026-08-15. "
                f"{company} AI engineer. Required skills: Python, PyTorch."
            )

        pipeline = RetrievalPipeline(registry, {"fixture": ConsultingProvider(results)}, page_fetcher=fetcher)
        return ConsultingAgent(pipeline)

    def _request(self, max_companies=10):
        metadata = UserConfirmedMetadata(
            items=[
                MetadataItem(
                    category="technical_skills",
                    normalized_value="Python, PyTorch",
                    provenance="USER_CORRECTED",
                    extraction_confidence=1.0,
                ),
                MetadataItem(
                    category="projects",
                    normalized_value="AI engineer project",
                    provenance="USER_CORRECTED",
                    extraction_confidence=1.0,
                ),
            ],
            preferences={"preferred_role": "AI engineer", "preparation_period": "3 months"},
            confirmed_at="2026-08-01T00:00:00Z",
            revision=1,
        )
        return ConsultingRequest(user_confirmed_metadata=metadata, max_companies=max_companies)

    def test_company_scoring_requirements_and_claim_evidence_links(self):
        results = [
            SearchResult(source_name="fixture", title="AI Engineer", url="https://example.com/alpha", query="AI engineer"),
            SearchResult(source_name="fixture", title="AI Engineer Intern", url="https://example.com/beta", query="AI engineer"),
        ]
        response, ledger = self._agent(results).analyze(self._request())

        self.assertEqual(len(response.companies), 2)
        self.assertTrue(all(company.score.deterministic_score >= 0 for company in response.companies))
        self.assertTrue(response.market_requirements)
        self.assertTrue(response.claims)
        for claim in ledger.claims:
            self.assertTrue(claim.evidence_ids)
            self.assertEqual(claim.current_verdict.value, "PENDING")
        self.assertFalse(response.reference_case_policy.accepted_case_implementation)

    def test_empty_retrieval_returns_partial_warning(self):
        response, ledger = self._agent([]).analyze(self._request())

        self.assertEqual(response.companies, [])
        self.assertTrue(response.partial)
        self.assertTrue(response.warnings)
        self.assertEqual(ledger.evidence, [])


if __name__ == "__main__":
    unittest.main()
