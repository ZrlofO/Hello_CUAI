import os
import unittest

from app.metadata.models import RawExtraction
from app.metadata.rephrase import _source_contains, rephrase_metadata


class MetadataRephraseTests(unittest.TestCase):
    def setUp(self):
        self.raw = RawExtraction(
            filename="cv.pdf",
            content_type="application/pdf",
            byte_size=10,
            page_count=1,
            extraction_method="test",
            page_text=[{"page": 1, "text": "Memory Plant 창업자 및 개발자\nPython, PyTorch"}],
        )

    def test_source_provenance_accepts_whitespace_variants(self):
        self.assertTrue(_source_contains(self.raw, 1, "Memory Plant 창업자   및 개발자"))
        self.assertFalse(_source_contains(self.raw, 1, "invented experience"))

    def test_rephrase_is_optional_without_api_key(self):
        previous = os.environ.pop("OPENAI_API_KEY", None)
        try:
            self.assertIsNone(rephrase_metadata(self.raw, "AI engineer", "3 months"))
        finally:
            if previous is not None:
                os.environ["OPENAI_API_KEY"] = previous


if __name__ == "__main__":
    unittest.main()
