import logging
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

chrome_paths = [
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    os.path.expandvars("%LOCALAPPDATA%/Google/Chrome/Application/chrome.exe"),
]

chrome_path = next((p for p in chrome_paths if Path(p).exists()), None)

BROWSER_DOMAINS = {
    "nature.com", "onlinelibrary.wiley.com", "pubs.acs.org",
    "sciencedirect.com", "link.springer.com", "dr.ntu.edu.sg",
}

#Инициализзация браузера
class BrowserDownloader:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout * 1000
        self._playwright = None
        self._browser = None

    def __enter__(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True, executable_path=chrome_path)
        return self

    def __exit__(self, *args):
       if self._browser:
           self._browser.close()
           if self._playwright:
               self._playwright.stop()
    
    #Скачивание через браузер
    def download(self, url: str) -> bytes | None:
        if not self._browser:
            logger.error("Браузер не найден")
            return None
        if not any(d in url for d in BROWSER_DOMAINS):
            return None
        try:
            page = self._browser.new_page()
            with page.expect_download(timeout=self.timeout) as download_info:
                page.goto(url, wait_until="networkidle")
            download = download_info.value
            path = download.path()
            with open(path, "rb") as f:
                return f.read()
        except Exception as exc:
            logger.warning("Ошибка скачивания через браузер для %s: %s", url, exc)
            return None
