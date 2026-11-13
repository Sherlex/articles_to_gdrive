import logging
import sys
import os

from config import Config
from .resolver import PdfResolver
from .downloader import PdfDownloader
from .gdrive_storage import DriveStorage, slugify
from .api_client import OpenAlexClient
from .browser_downloader import BrowserDownloader

#Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("export.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")

#Загружаем список авторов из txt файла
def load_authors(path: str) -> list[tuple[str, str | None]]:
    authors = []
    try:
        with open(path, encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                name, _, oa_id = line.partition("|")
                authors.append((name.strip(), oa_id.strip() or None))
    except FileNotFoundError:
        logger.error("Файл с автором не найден: %s", path)
    return authors


def main() -> None:
    config= Config()
    authors = load_authors(config.authors_file)
    if not authors:
        logger.error("Список авторов пустой")
        return
    client = OpenAlexClient(config.openAlex_email, config.request_delay)
    downloader = PdfDownloader(config.timeout, config.retries, config.max_pdf_mb)
    resolver = PdfResolver(config.openAlex_email, timeout=config.timeout)
    storage = DriveStorage(config.google_credentials_key,
                           config.google_token_key,
                           config.drive_folder,
                           root_folder_id=config.drive_folder_id or None)
    stats = {"ok": 0, "fail": 0}
    for name, oa_id in authors:
        logger.info("=== Автор: %s ===", name)
        author = client.get_author_by_id(oa_id) if oa_id else client.find_author(name)
        if not author:
            continue
        author_folder = slugify(author.get("display_name", name))
        author_folder_id = storage.get_or_create_folder(author_folder, parent_id=storage.root_id)
        index = []
        missing = []
        downloaded = 0
        with BrowserDownloader() as browser:
            #Перебираем статьи пока не скачаем нужное количество
            for work in client.iter_open_access_works(author["id"]):
                if downloaded >= config.articles_per_author:
                    break
                #Перебираем url-ы пока не найдем работающий
                pdf = None
                source_url = None
                for url in work.pdf_urls:
                    pdf = downloader.download(url)
                    if pdf:
                        source_url = url
                        break
                    if not pdf:
                        pdf = browser.download(url)
                if not pdf:
                    extra_urls = resolver.find_extra_pdf_urls(work.doi, work.landing_urls)
                    for url in extra_urls:
                        pdf = downloader.download(url)
                        if pdf:
                            source_url = url
                            break
                        pdf = browser.download(url)
                        if pdf:
                            source_url = url
                            break
                #Если pdf не скачался    
                if pdf is None:
                    logger.warning("Не удалось скачать: %s", work.title)
                    missing.append({"title": work.title,
                                    "doi": work.doi,
                                    "year": work.year,
                                    "publisher_page": 
                                    work.landing_urls[0] if work.landing_urls else None,
                                    "openalex_id": work.openalex_id,
                                    })
                    continue
                downloaded += 1
                filename = f"{downloaded:02d}_{slugify(work.title)}.pdf"
                #Если статья загружена на Диск
                if storage.upload_article(author_folder_id, filename, pdf): 
                    stats["ok"] += 1
                    index.append({"file": filename, "title": work.title, 
                                "year": work.year, "doi": work.doi, "source_pdf": source_url,})
                    logger.info("Успешно %d/%d: %s", downloaded, config.articles_per_author, work.title[:60])
                else:
                    stats["fail"] += 1
                    downloaded -= 1
            #Если не загружено необходимое количество статей для автора
            if downloaded < config.articles_per_author:
                logger.warning("Для автора %s найдено только %d доступных статей (нужно %d)",
                            name, downloaded, config.articles_per_author)
            storage.upload_json(author_folder_id, "index.json", {
                "author": author.get("display_name"),
                "openalex_id": author["id"],
                "works-count": author.get("works_count"),
                "articles_downloaded": downloaded,
                "articles": index,
            })
            #Если были статьи с закрытым доступом, формируем лог файл
            if missing:
                storage.upload_json(author_folder_id, "missing.json",
                                    {
                                        "author": author.get("display_name"),
                                        "openalex_id": author["id"],
                                        "missing-count": len(missing),
                                        "note": ("Статей нет в открытом доступе."),
                                        "articles": missing,
                                    })

#Если пользователь остановил поиск
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Остановлено пользователем." 
                    "Загруженные файлы сохранены на Диск")
        sys.exit(0)
    