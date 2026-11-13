import logging
import time
import requests
import random

from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup
from config import Config

logger = logging.getLogger(__name__)

#Браузерные заголовки
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"),
                   "Accept":
                   "application/pdf, application/xhtml+xml,*/*;q=0.8",
                   "Accept-Language": "en-US,en;q=0.9",
}

DOMAIN_REPLACEMENTS = {
   "advances.sciencemag.org": "www.science.org",
    "science.sciencemag.org": "www.science.org",
}

#Нормализуем url
def normalize_url(url: str) -> str:
    for old, new in DOMAIN_REPLACEMENTS.items():
        if old in url:
            return url.replace(old, new)
    return url

class PdfDownloader:
    def __init__(self, timeout=Config.timeout, retries=Config.retries, max_mb=Config.max_pdf_mb):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.timeout, self.retries = timeout, retries
        self.max_bytes = max_mb * 1024 * 1024

    #Скачиваем PDF файл
    def download(self, url: str) -> bytes | None:
        url = normalize_url(url)
        for attempt in range(1, self.retries + 1):
            try:
                r = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            except requests.RequestException as exc:
                logger.warning("Сетевая ошибка %s: %s (попытка %d)", url, exc, attempt)
                time.sleep(2 * attempt)
                continue
            if r.status_code == 200:
                if len(r.content) > self.max_bytes:
                    logger.warning("PDF файл слишком большой: %s", url)
                    return None
                is_pdf = (r.content.lstrip()[:5] or "pdf" in r.headers.get("Content-Type", "").lower())
                if not is_pdf:
                    logger.warning("Это не PDF файл: %s", url)
                    return None
                return r.content
            if r.status_code in (401, 403, 404, 410):
                logger.warning("HTTP %s (пропуск): %s", r.status_code, url)
                return None
            logger.warning("HTTP %s: %s (попытка %d)", r.status_code, url, attempt)
            time.sleep(2 * attempt)
        return None




