import unittest

from app.evidence.ledger import EvidenceLedger
from app.retrieval.models import RetrievalRequest, SearchResult
from app.retrieval.pipeline import RetrievalPipeline
from app.retrieval.registry import SourcePolicy, SourceRegistry


class FixtureProvider:
    def __init__(self, results):
        self.results = results

    def search(self, query, limit):
        return [item.model_copy(update={"query": query}) for item in self.results[:limit]]


class RetrievalFixtureTests(unittest.TestCase):
    def setUp(self):
        self.registry = SourceRegistry(
            sources=[
                SourcePolicy(
                    name="fixture",
                    publisher="Fixture Official",
                    source_type="OFFICIAL_COMPANY",
                    quality_threshold=0.8,
                )
            ]
        )
        self.result = SearchResult(
            source_name="fixture",
            title="AI Engineer",
            url="https://example.com/jobs/1#details",
            snippet="Python and PyTorch required",
            query="AI engineer",
        )

    def test_deduplication_and_original_page_evidence(self):
        provider = FixtureProvider([self.result, self.result.model_copy(update={"url": "https://EXAMPLE.com/jobs/1"})])

        def fetcher(url):
            return 200, "text/html", (
                "Official posting. Published: 2026-07-01. "
                "Application deadline: 2026-08-15. Python and PyTorch required."
            )

        response, ledger = RetrievalPipeline(
            self.registry,
            {"fixture": provider},
            page_fetcher=fetcher,
        ).run(RetrievalRequest(intent="hiring requirements", target_role="AI engineer", limit=10))

        self.assertEqual(len(response.search_results), 1)
        self.assertEqual(len(response.pages), 1)
        self.assertEqual(len(ledger.evidence), 1)
        self.assertEqual(ledger.evidence[0].application_deadline.isoformat(), "2026-08-15")
        self.assertTrue(ledger.evidence[0].active_status_verified)
        self.assertEqual(ledger.evidence[0].source_url, "https://example.com/jobs/1#details")

    def test_restricted_page_is_not_saved_as_evidence(self):
        def fetcher(url):
            return 403, "text/html", "forbidden"

        response, ledger = RetrievalPipeline(
            self.registry,
            {"fixture": FixtureProvider([self.result])},
            page_fetcher=fetcher,
        ).run(RetrievalRequest(intent="requirements", target_role="AI engineer"))

        self.assertEqual(len(ledger.evidence), 0)
        self.assertTrue(response.pages[0].restricted)

    def test_timeout_degrades_to_warning(self):
        def fetcher(url):
            raise TimeoutError("fixture timeout")

        response, ledger = RetrievalPipeline(
            self.registry,
            {"fixture": FixtureProvider([self.result])},
            page_fetcher=fetcher,
        ).run(RetrievalRequest(intent="requirements", target_role="AI engineer"))

        self.assertEqual(len(ledger.evidence), 0)
        self.assertEqual(response.pages[0].retrieval_error, "TimeoutError")


if __name__ == "__main__":
    unittest.main()
