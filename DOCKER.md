# Запуск проекта в Docker

## Требования

- Docker + Docker Compose
- Файл `.env` в корне проекта (скопируй из `.env.example` и заполни)

## Первый запуск (важно!)

Telethon требует интерактивной авторизации по номеру телефона при первом запуске.
Это нужно сделать **локально**, до запуска в Docker.

```bash
# 1. Создай виртуальное окружение и установи зависимости
python -m venv .venv
source .venv/bin/activate
pip install -e .

# 2. Авторизуй юзербота (введи код из SMS/Telegram)
python -m userbot.main

# После успешной авторизации в папке sessions/ появится файл *.session
# Ctrl+C — останавливаем, дальше запускаем через Docker
```

## Сборка и запуск

```bash
# Собрать образы и запустить оба сервиса
docker compose up --build -d

# Посмотреть логи
docker compose logs -f

# Логи отдельного сервиса
docker compose logs -f bot
docker compose logs -f userbot
```

## Остановка

```bash
docker compose down
```

## Обновление после изменений в коде

```bash
docker compose up --build -d
```

## Структура томов

| Хост              | Контейнер       | Содержимое                          |
|-------------------|-----------------|-------------------------------------|
| `./data`          | `/app/data`     | SQLite БД + скачанные фото (media/) |
| `./sessions`      | `/app/sessions` | Файл сессии Telethon (только userbot)|

## Переменные окружения (.env)

```env
BOT_TOKEN=...        # Токен бота от @BotFather
API_ID=...           # Telegram API ID (my.telegram.org)
API_HASH=...         # Telegram API Hash
PHONE_NUMBER=...     # Номер телефона аккаунта юзербота (+79...)
DB_PATH=data/database.db
LOG_LEVEL=INFO
```

## Полезные команды

```bash
# Зайти в контейнер бота
docker compose exec bot sh

# Посмотреть состояние контейнеров
docker compose ps

# Пересобрать только один сервис
docker compose up --build -d bot
```
