import unittest
from unittest.mock import MagicMock, patch

from semantic_scholar_client import (
    GRAPH_BASE_URL,
    RECOMMENDATIONS_BASE_URL,
    SemanticScholarClient,
)


class SemanticScholarClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = SemanticScholarClient(api_key="test-key")

    def test_init_sets_api_key_header(self) -> None:
        self.assertEqual(self.client.session.headers.get("x-api-key"), "test-key")

    @patch("semantic_scholar_client.requests.Session.get")
    def test_search_papers_calls_expected_endpoint_and_clamps_limit(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": []}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = self.client.search_papers("rlhf verifier", limit=200, year="2024")

        self.assertEqual(result, {"data": []})
        mock_get.assert_called_once()
        called_url = mock_get.call_args.kwargs["url"] if "url" in mock_get.call_args.kwargs else mock_get.call_args.args[0]
        called_params = mock_get.call_args.kwargs["params"]
        self.assertEqual(called_url, f"{GRAPH_BASE_URL}/paper/search")
        self.assertEqual(called_params["query"], "rlhf verifier")
        self.assertEqual(called_params["limit"], 50)
        self.assertEqual(called_params["year"], "2024")
        self.assertIn("title", called_params["fields"])

    @patch("semantic_scholar_client.requests.Session.get")
    def test_get_paper_details_calls_expected_endpoint(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"paperId": "abc123"}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = self.client.get_paper_details("abc123")

        self.assertEqual(result["paperId"], "abc123")
        called_url = mock_get.call_args.kwargs["url"] if "url" in mock_get.call_args.kwargs else mock_get.call_args.args[0]
        self.assertEqual(called_url, f"{GRAPH_BASE_URL}/paper/abc123")

    @patch("semantic_scholar_client.requests.Session.get")
    def test_recommend_papers_calls_expected_endpoint_and_clamps_limit(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"recommendedPapers": []}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = self.client.recommend_papers("seed-paper", limit=0)

        self.assertEqual(result, {"recommendedPapers": []})
        called_url = mock_get.call_args.kwargs["url"] if "url" in mock_get.call_args.kwargs else mock_get.call_args.args[0]
        called_params = mock_get.call_args.kwargs["params"]
        self.assertEqual(called_url, f"{RECOMMENDATIONS_BASE_URL}/papers/forpaper/seed-paper")
        self.assertEqual(called_params["limit"], 1)

    def test_read_full_paper_text_returns_reason_when_no_open_access_pdf(self) -> None:
        with patch.object(self.client, "get_open_access_pdf_url", return_value=None):
            result = self.client.read_full_paper_text("missing-oa-paper")

        self.assertFalse(result["success"])
        self.assertIn("No open-access PDF URL available", result["reason"])

    @patch("semantic_scholar_client.fitz.open")
    @patch("semantic_scholar_client.requests.Session.get")
    def test_read_full_paper_text_success_and_truncation(
        self, mock_get: MagicMock, mock_fitz_open: MagicMock
    ) -> None:
        with patch.object(
            self.client, "get_open_access_pdf_url", return_value="https://example.org/paper.pdf"
        ):
            pdf_response = MagicMock()
            pdf_response.content = b"%PDF-1.7 mock"
            pdf_response.raise_for_status.return_value = None
            mock_get.return_value = pdf_response

            page_1 = MagicMock()
            page_1.get_text.return_value = "A" * 40
            page_2 = MagicMock()
            page_2.get_text.return_value = "B" * 40
            mock_doc = MagicMock()
            mock_doc.__iter__.return_value = [page_1, page_2]
            mock_fitz_open.return_value = mock_doc

            result = self.client.read_full_paper_text("paper-1", max_chars=30)

        self.assertTrue(result["success"])
        self.assertEqual(result["paper_id"], "paper-1")
        self.assertEqual(result["pdf_url"], "https://example.org/paper.pdf")
        self.assertIn("...[truncated]...", result["text"])
        mock_get.assert_called_once_with("https://example.org/paper.pdf", timeout=self.client.timeout_seconds)
        mock_doc.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
