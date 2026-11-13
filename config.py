import os
from dataclasses import dataclass, field
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

@dataclass
class Config: 
    #Количество статей каждого автора
    articles_per_author: int = int(field(default_factory=lambda: os.getenv("ARTICLES_PER_AUTHOR", "")))
    request_delay: float = 0.3
    timeout: int = 30
    retries: int = 2
    max_pdf_mb: int = 15

    #API для поиска и выгрузки
    openAlex_email: str = field(default_factory=lambda: os.getenv("OPENALEX_EMAIL", ""))

    # Google Диск
    
    drive_folder: str = field(default_factory=lambda: os.getenv("DRIVE_FOLDER", ""))
    drive_folder_id: str = field(default_factory=lambda: os.getenv("DRIVE_FOLDER_ID", ""))
    google_credentials_key: str = "credentials.json"
    google_token_key: str = "token.json"

    authors_file: str = str(BASE_DIR  / "authors.txt")

