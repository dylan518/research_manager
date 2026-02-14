import os
import tempfile
from typing import Any, Dict, Optional

import fitz
import requests


GRAPH_BASE_URL = "https://api.semanticscholar.org/graph/v1"
RECOMMENDATIONS_BASE_URL = "https://api.semanticscholar.org/recommendations/v1"


class SemanticScholarClient:
    def __init__(self, api_key: Optional[str] = None, timeout_seconds: int = 30) -> None:
        self.api_key = api_key or os.getenv("S2_KEY")
        if not self.api_key:
            raise ValueError("Missing S2_KEY. Set it in your environment or .env file.")
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({"x-api-key": self.api_key})

    def _get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        response = self.session.get(url, params=params, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()

    def search_papers(self, query: str, limit: int = 10, year: Optional[str] = None) -> Dict[str, Any]:
        fields = ",".join(
            [
                "title",
                "authors",
                "year",
                "abstract",
                "url",
                "venue",
                "citationCount",
                "influentialCitationCount",
                "openAccessPdf",
                "externalIds",
            ]
        )
        params: Dict[str, Any] = {
            "query": query,
            "limit": max(1, min(limit, 50)),
            "fields": fields,
        }
        if year:
            params["year"] = year
        return self._get(f"{GRAPH_BASE_URL}/paper/search", params=params)

    def get_paper_details(self, paper_id: str) -> Dict[str, Any]:
        fields = ",".join(
            [
                "title",
                "authors",
                "year",
                "abstract",
                "url",
                "venue",
                "citationCount",
                "influentialCitationCount",
                "openAccessPdf",
                "externalIds",
                "references.title",
                "references.paperId",
                "citations.title",
                "citations.paperId",
            ]
        )
        return self._get(f"{GRAPH_BASE_URL}/paper/{paper_id}", params={"fields": fields})

    def recommend_papers(self, paper_id: str, limit: int = 10) -> Dict[str, Any]:
        fields = ",".join(
            [
                "title",
                "authors",
                "year",
                "abstract",
                "url",
                "venue",
                "citationCount",
                "openAccessPdf",
                "externalIds",
            ]
        )
        params = {"limit": max(1, min(limit, 50)), "fields": fields}
        return self._get(f"{RECOMMENDATIONS_BASE_URL}/papers/forpaper/{paper_id}", params=params)

    def get_open_access_pdf_url(self, paper_id: str) -> Optional[str]:
        details = self.get_paper_details(paper_id)
        pdf_obj = details.get("openAccessPdf") or {}
        return pdf_obj.get("url")

    def read_full_paper_text(self, paper_id: str, max_chars: int = 15000) -> Dict[str, Any]:
        pdf_url = self.get_open_access_pdf_url(paper_id)
        if not pdf_url:
            return {
                "paper_id": paper_id,
                "success": False,
                "reason": "No open-access PDF URL available from Semantic Scholar for this paper.",
            }

        pdf_response = self.session.get(pdf_url, timeout=self.timeout_seconds)
        pdf_response.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp_pdf:
            tmp_pdf.write(pdf_response.content)
            tmp_pdf.flush()

            doc = fitz.open(tmp_pdf.name)
            all_text = []
            for page in doc:
                all_text.append(page.get_text("text"))
            doc.close()

        full_text = "\n".join(all_text).strip()
        if len(full_text) > max_chars:
            full_text = full_text[:max_chars] + "\n\n...[truncated]..."

        return {
            "paper_id": paper_id,
            "success": True,
            "pdf_url": pdf_url,
            "text": full_text,
        }
