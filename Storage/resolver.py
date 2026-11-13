import logging
import re
import time
import requests

from urllib.parse import urljoin
from config import Config

logger = logging.getLogger(__name__)

_CITATION_PDF = re.compile( r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,)

_CITATION_PDF_ALT = re.compile( r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']citation_pdf_url["\']',
    re.IGNORECASE,)

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"),
                   "Accept":
                   "application/pdf, application/xhtml+xml,*/*;q=0.8",
                   "Accept-Language": "en-US,en;q=0.9",
}

#Поиск PDF в запасных источниках, если через OpenAlex не нашли прямых ссылок
class PdfResolver:
    def __init__(self, email: str, timeout: int = 30):
        self.email = email
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    #Собираем ссылки из всех источников
    def find_extra_pdf_urls(self, doi: str | None, landing_urls: list[str]) -> list[str]:
        urls: list[str] = []
        if doi:
            urls.extend(self._from_unpaywall(doi))
            urls.extend(self._from_semanthic_scholar(doi))
            urls.extend(self._from_pmc(doi))
        for page in landing_urls[:3]:
            pdf = self._from_landing_page(page)
            if pdf:
                urls.append(pdf)
        seen, unique = set(), []
        for url in urls:
            if url not in seen:
                seen.add(url)
                unique.append(url)
        return unique

    #
    def _from_unpaywall(self, doi: str) -> list[str]:
        try:
            r = self.session.get(f"https://api.unpaywall.org/v2/{doi}",
                                 params={"email": self.email}, timeout=self.timeout,
                                 )
            if r.status_code != 200:
                return []
            data = r.json()
            urls = []
            best = data.get("best_oa_location") or {}
            if best.get("url_for_pdf"):
                urls.append(best["url_for_pdf"])
            for location in data.get("oa_locations") or []:
                if location.get("url_for_pdf"):
                    urls.append(location["url_for_pdf"])
            time.sleep(0.2)
            return urls
        except requests.RequestException as exc:
            logger.debug("Unpaywall недоступен для %s: %s", doi, exc)
            return []

    def _from_semanthic_scholar(self, doi: str) -> list[str]:
        try:
            r = self.session.get(f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
                                 params={"fields": "openAccessPdf"}, timeout=self.timeout,
                                 )
            time.sleep(1.0)
            if r.status_code != 200:
                return []
            pdf = (r.json().get("openAccessPdf") or {}).get("url")
            return [pdf] if pdf else []
        except requests.RequestException as exc:
            logger.debug("Semantic Scholar недоступен для %s: %s", doi, exc)
            return []

    def _from_pmc(self, doi: str) -> list[str]:
            try:
                r = self.session.get("https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/",
                                     params={"ids": doi, "format": "json"}, timeout=self.timeout,
                                     )
                data = r.json()
                pmcid = data.get("records", [{}])[0].get("pmcid")
                if pmcid:
                    return [f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"]
            except Exception:
                pass
            return []
    #Ищем ссылку на статью на HTML странице
    def _from_landing_page(self, url: str) -> str | None:
        try:
            r = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            if r.status_code != 200 or "text/html" not in r.headers.get("Content-Type", ""):
                return None
            match = _CITATION_PDF.search(r.text) or _CITATION_PDF_ALT.search(r.text)
            if match:
                pdf_url = urljoin(r.url, match.group(1))
                logger.info("Найден PDF на странице %s", url)
                return pdf_url
        except requests.RequestException as exc:
            logger.debug("Landing-страница недоступна %s: %s", url, exc)
        return None
