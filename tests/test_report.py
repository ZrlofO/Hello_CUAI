import unittest

from app.metadata.models import NormalizedMetadata, PreferenceInformation, RawExtraction, WorkflowState
from app.report.service import build_final_report


class FinalReportFixtureTests(unittest.TestCase):
    def workflow(self):
        return WorkflowState(
            request_id="request-report",
            workflow_id="workflow-report",
            status="LEADING_AGENT_INITIALIZED",
            pdf=RawExtraction(
                filename="cv.pdf",
                content_type="application/pdf",
                byte_size=12,
                extraction_method="fixture",
            ),
            normalized_metadata=NormalizedMetadata(
                preferences=PreferenceInformation(preferred_role="AI Engineer", preparation_period="3 months")
            ),
            claims=[{
                "claim_id": "claim-1",
                "claim_text": "The profile includes Python experience",
                "claim_type": "user_fact",
                "evidence_ids": [],
            }],
            evidence_ledger={"claims": [], "evidence": [], "warnings": []},
        )

    def test_partial_report_preserves_uncertainty(self):
        report = build_final_report(self.workflow())

        self.assertEqual(report.status, "PARTIAL")
        self.assertEqual(report.summary["preferred_role"], "AI Engineer")
        self.assertTrue(report.uncertainty_notes)
        self.assertEqual(report.citations, [])

    def test_citations_only_include_evidence_with_urls(self):
        workflow = self.workflow()
        workflow.evidence_ledger = {
            "claims": [],
            "warnings": [],
            "evidence": [
                {"evidence_id": "e-1", "source_url": "https://example.com/job", "source_title": "Job", "verification_status": "VERIFIED"},
                {"evidence_id": "e-2", "source_title": "No URL"},
            ],
        }

        report = build_final_report(workflow)

        self.assertEqual([item["evidence_id"] for item in report.citations], ["e-1"])


if __name__ == "__main__":
    unittest.main()
