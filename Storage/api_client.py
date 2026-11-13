import logging
import time
import requests

from dataclasses import dataclass
from collections.abc import Iterator

logger = logging.getLogger(__name__)

BASE_URL = "https://api.openalex.org"

@dataclass
class Work:
    title: str
    year: int | None
    doi: str | None
    pdf_urls: list[str]
    landing_urls: list[str]
    openalex_id: str

class OpenAlexClient:
    
    TRUSTED_HOSTS = ("arxiv.org", "ncbi.nlm.nih.gov", "doaj.org", "hal.science",
                 "biorxiv.org", "medrxiv.org", "ssrn.com", "osf.io",
                 "figshare.com", ".edu", "core.ac.uk")

    def __init__(self, email: str, delay: float = 0.3, timeout: int = 30, retries: int = 3):
        self.session = requests.Session()
        self.params = {"mailto": email} if email else {}
        self.delay, self.timeout, self. retries = delay, timeout, retries

    #Ищем автора по имени
    def find_author(self, name: str) -> dict | None:
        data = self._get(f"{BASE_URL}/authors",
                        params={"search": name, "per-page": 1})
        results = (data or {}).get("results", [])
        if not results:
            logger.warning("Автор не найден: %s", name)
            return None
        author = results[0]
        inst = (author.get("last_known_institutions") or [{}])[0].get("display-name", "?")
        logger.info("'%s' -> %s | %s | работ: %s", name, author["id"], inst, author.get("works_count"))
        return author

    #Если есть id автора
    def get_author_by_id(self, short_id: str) -> dict | None:
        return self._get(f"{BASE_URL}/authors/{short_id}")

    #Находим список открытых статей автора по убыванию цитируемости
    def iter_open_access_works(self, author_id: str) -> Iterator[Work]:
        cursor = "*"
        short_id = author_id.rsplit("/", 1)[-1]
        while True:
            data = self._get(f"{BASE_URL}/works", 
                             params={
                                 "filter": f"author.id:{short_id}",
                                 "sort": "cited_by_count:desc",
                                 "per-page": 200,
                                 "cursor": cursor,
                             })
            if not data: 
                break
            results = data.get("results", [])
            if not results:
                break
            for item in results:
                pdf_urls = self._extract_pdf_urls(item)
                landing_urls = self._extract_landing_urls(item)
                if pdf_urls or landing_urls:
                    yield Work(title=item.get("title") or "untitled", 
                               year=item.get("publication_year"), doi=item.get("doi"),
                               pdf_urls=pdf_urls,landing_urls=landing_urls, 
                               openalex_id=item.get("id", ""))
            next_cursor = (data.get("meta") or {}).get("next_cursor")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

    #Ищем ссылки на статьи pdf       
    @classmethod
    def _extract_pdf_urls(cls, item: dict) -> list[str]:
        urls: list[str] = []
        for key in ("best_oa_location", "primary_location"):
            location = item.get(key) or {}
            if location.get("pdf_url") and location["pdf_url"] not in urls:
                urls.append(location["pdf_url"]) 
        for location in item.get("locations") or []:
            if location.get("pdf_url") and location["pdf_url"] not in urls:
                urls.append(location["pdf_url"])
        trusted = [u for u in urls if any(h in u for h in cls.TRUSTED_HOSTS)]
        rest = [u for u in urls if u not in trusted]
        return trusted + rest

    #метод для GET запроса с повторными попытками
    def _get(self, url: str, params: dict | None = None) -> dict | None:
        merged = {**self.params, **(params or {})}
        for attempt in range (1, self.retries + 1):
            try:
                r = self.session.get(url, params=merged, timeout=self.timeout)
                if r.status_code == 200:
                    time.sleep(self.delay)
                    return r.json()
                if r.status_code == 404:
                    return None
                logger.warning("HTTP %s: %s (попытка %d)", r.status_code, url, attempt)
            except requests.RequestException as exc:
                logger.warning("Ошибка %s: %s (попытка %d)", url, exc, attempt)
                time.sleep(self.delay * attempt * 2)
        return None

    #Ищем дополнительные ссылки на страницы статей (если нет прямых ссылок)
    @staticmethod
    def _extract_landing_urls(item: dict) -> list[str]:
        urls: list[str] = []
        for key in ("best_oa_location", "primary_location"):
            location = item.get(key) or {}
            url = location.get("landing_page_url")
            if url and url not in urls:
                urls.append(url)
        for location in item.get("locations") or []:
            url = location.get("landing_page_url")
            if url and url not in urls:
                urls.append(url)
        return urls

        


  