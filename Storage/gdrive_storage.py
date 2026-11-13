import io
import json
import logging
import  re
import time
from pathlib import Path

from google.auth.transport.requests import Request
from google.auth.credentials import Credentials
from google.oauth2.credentials import Credentials as OAuthCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
from typing import Any

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_MIME = "application/vnd.google-apps.folder"

#Превращаем заголовок статьи в имя файла
def slugify(text: str, max_len: int = 100) -> str: 
    text = re.sub(r"[^\w\s-]", "", text, flags = re.UNICODE)
    text = re.sub(r"\s+", "_", text.strip())
    return text[:max_len] or "untitled"

#Загрузка на диск
class DriveStorage:   
    #Инициализация
    def __init__(self, credentials_file: str, token_file: str, root_folder: str,
                 root_folder_id: str | None = None):
        creds = self._authorize(credentials_file, token_file)
        self.service = build("drive", "v3", credentials=creds)
        if root_folder_id:
            self.root_id = self._resolve_existing_folder(root_folder_id, root_folder)
        else:
            self.root_id = self.get_or_create_folder(root_folder)
            logger.info("Корневая папка на Диске: '%s' (id=%s)", root_folder, self.root_id)
    
    #Поиск папки по ID
    def _resolve_existing_folder(self, folder_id: str, fallback_name: str) -> str:
        try:
            meta = self._execute(self.service.files().get(fileId=folder_id, fields="id,name,mimeType", supportsAllDrives=True,
            ))
            if meta is None:
                raise RuntimeError(f"Не удалось получить метаданные папки id={folder_id}")
        except HttpError as exc:
            if exc.status_code in (403, 404):
                logger.warning("Папка id=%s недоступна (HTTP %s) - ищу/создаю папку '%s'",
                               folder_id, exc.status_code, fallback_name)
                return self.get_or_create_folder(fallback_name)
            raise
        if meta.get("mimeType") != FOLDER_MIME:
            raise ValueError(f"DRIVE_FOLDER_ID={folder_id} выбран файл, а не папка."
                             f"Укажите ID из URL папки.")
        logger.info("Корневая папка на Диске: '%s' (id=%s)", meta["name"], meta["id"])
        return meta["id"]

    #Авторизация
    @staticmethod
    def _authorize(credentials_file: str, token_file: str) -> Credentials:
        creds = None
        if Path(token_file).exists():
            creds = OAuthCredentials.from_authorized_user_file(token_file, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)
            Path(token_file).write_text(creds.to_json(), encoding="utf-8")
        return creds

    #Создаем папку или получаем доступ к существующей
    def get_or_create_folder(self, name: str, parent_id: str | None = None) -> str:
        query = f"mimeType='{FOLDER_MIME}' and name='{self._escape(name)}' and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"
        found = self._list_files(query)
        if found:
            return found[0] ["id"]
        metadata: dict[str, Any] = {"name": name, "mimeType": FOLDER_MIME}
        if parent_id:
            metadata["parents"] = [parent_id]
        folder = self._execute(self.service.files().create(body=metadata, fields="id", 
                                                           supportsAllDrives=True,))
        logger.info("Создана папка на Диске: %s", name)
        return folder["id"]

    #Загружаем статьи на Диск
    def upload_article(self, folder_id: str, 
                       filename: str, data: bytes, mime: str = "application/pdf", 
                       overwrite: bool = False) -> bool: 
        existing = self._find_file(filename, folder_id)
        if existing and not overwrite:
            logger.info("Документ уже на диске, пропустить: %s", filename)
            return True
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime, resumable=True)
        try:
            if existing: 
                self._execute(self.service.files().update(fileId=existing["id"], media_body=media, 
                                                          supportsAllDrives=True,))
            else: 
                metadata = {"name": filename, "parents": [folder_id]}
                request = self.service.files().create(body=metadata, media_body = media, fields = "id",
                                                      supportsAllDrives=True,)
                response = None
                while response is None:
                    #Загрузка по частям
                    _, response = request.next_chunk()
            logger.info("Загружено на Диск: %s", filename)
            return True
        except HttpError as exc:
            logger.error("Ошибка загрузки %s: %s", filename, exc)
            return False

        
    #Загружаем файл с информацией о статьях
    def upload_json(self, folder_id: str, filename: str, obj: dict, overwrite: bool = True) -> bool:
        data = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        return self.upload_article(folder_id, filename, data, mime="application/json", overwrite=overwrite)

    #Ищем файл по имени в папке
    def _find_file(self, name: str, parent_id: str) -> dict | None:
        query = (f"name='{self._escape(name)}' and '{parent_id}' in parents "
                 f"and trashed=false and mimeType!='{FOLDER_MIME}' ")
        found = self._list_files(query)
        return found[0] if found else None

    #Поисковый запрос
    def _list_files(self, query: str) -> list[dict]:
        result = self._execute(self.service.files().list(q=query, spaces="drive", 
                                                         fields="files(id, name)", pageSize=10,
                                                         supportsAllDrives=True, includeItemsFromAllDrives=True,))
        return result.get("files", [])

    #Повторяем запрос при ошибке API
    @staticmethod
    def _execute(request, retries: int = 5) -> dict[str, Any]:
        for attempt in range(1, retries + 1):
            try:
                result = request.execute()
            except HttpError as exc:
                if exc.status_code in (403, 429, 500, 502, 503) and attempt < retries:
                    time.sleep(2 ** attempt)
                    continue
                raise
            if result is None:
                raise RuntimeError("Drive API вернул пустой ответ")
            return result
        raise RuntimeError("Слишком много попыток")

    #Экранирование поисковых запросов
    @staticmethod
    def _escape(name: str) -> str:
        return name.replace("\\", "\\\\").replace("'", "\\'")

    
