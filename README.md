# Articles to Google Drive

Скрипт для скачивания научных статей авторов из открытых источников и загрузки их на Google Диск.

## Что делает

- Ищет автора в OpenAlex по имени
- Находит его статьи в открытом доступе
- Скачивает PDF из списка источников (OpenAlex, arXiv, Semantic Scholar, CORE, Europe PMC и др.)
- Загружает на Google Диск в папку автора

## Особенности

- Поиск статей по имени автора
- Многоисточниковое скачивание: OpenAlex, Unpaywall, Semantic Scholar, arXiv, CORE, Europe PMC
- Обход защиты издателей через Playwright (Wiley, Nature, ACS)
- Загрузка на Google Диск с организацией по папкам авторов
- Отчёт о недоступных статьях (`missing.json`)

## Установка

```bash
# 1. Клонировать репозиторий или скачать файлы проекта
git clone <url>
cd articles_to_gdrive

# 2. Создать виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# 3. Установить зависимости
pip install -r requirements.txt

# 4. Для обхода защиты издателей
playwright install chromium
```

## Подготовка к работе
### Настройка Google Drive API

1. Создайте проект на console.cloud.google.com
2. Включите Google Drive API
3. Создайте OAuth 2.0 Client ID (Desktop app)
4. Скачайте credentials.json в корень проекта

### Получение ID папки на Google Диске

1. Создайте папку на вашем Google Диске, куда будут сохраняться статьи.
2. Откройте её в браузере и скопируйте ID из адресной строки (часть после /folders/).

### Файл .env

Скопируйте .env.example в .env и заполните данные:
```bash
# OpenAlex (ваш email для API)
OPENALEX_EMAIL=your@email.com

# Google Диск
DRIVE_FOLDER=Научные статьи #Название вашей папки на диске
DRIVE_FOLDER_ID=            #ID существующей папки

ARTICLES_PER_AUTHOR=100     #Количество статей каждого автора
```
### Список авторов Storage/authors.txt

Формат: Имя Фамилия

## Запуск

```bash
python -m Storage.main
```
При первом запуске откроется браузер для авторизации Google. После подтверждения создастся файл token.json — дальше авторизация не требуется.

## Структура проекта

```
articles-to-gdrive/
├── Storage/
│   ├── __init__.py
│   ├── main.py                 # точка входа
│   ├── api_client.py           # поиск авторов и статей
│   ├── downloader.py           # скачивание PDF
│   ├── resolver.py             # запасные источники
│   ├── browser_downloader.py   # Playwright для защищённых сайтов
│   ├── gdrive_storage.py       # загрузка на Google Диск
│   └── .env                    # переменные окружения (создан редактированием .env.example)
├── credentials.json            # OAuth-ключ Google (получен на этапе настройки Google Drive API)
├── config.py                   # конфигурация
├── authors.txt                 # список авторов
├── requirements.txt            # список зависимостей
└── README.md
```
## Ограничения

* Ошибки 403 / Пустые PDF: Крупные издатели используют защиту от ботов (Cloudflare). Скрипт пытается обойти её с помощью Playwright, но это не гарантирует 100% шанс успеха.
* Файл missing.json: После завершения работы скрипта проверьте отчет о недоступных статьях. Там будут лежать имя автора и названия статей, которые не удалось скачать по разным причинам. Вы можете скопировать информацию и скачать их вручную через браузер.
* Квоты Google Drive: Загрузка идет от вашего имени (OAuth), поэтому файлы занимают место на вашем личном Google Диске. Убедитесь, что там достаточно свободного места для загрузки всех статей.