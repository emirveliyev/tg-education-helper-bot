# TG Education Helper Bot 📚🤖

**Дата:** 28.09.2025  

**Версия:** 1.0.0  
**Автор:** Rustem Emir-Veliyev  

Телеграм-бот — помощник для учителя.  
Позволяет генерировать и изменять тесты с помощью ИИ, искать материалы в Википедии и сохранять результаты для учеников.  
Бот автоматизирует подготовку заданий, помогает создавать СОР/СОЧ и управлять историей пользователей.  

---

## Возможности
- Генерация тестов по предметам, темам, классам и языкам.  
- Экспорт заданий в Word (вариант для учеников и ответы для учителя).  
- Изменение вопросов (смена темы или переменных).  
- Поиск информации в Википедии и выгрузка текста в Word.  
- Сохранение тестов в JSON для анализа.  
- Регистрация пользователей с подтверждением телефона.  
- Админ-панель: список пользователей, статистика, рассылки.  

---

## Установка и запуск
```bash
git clone https://github.com/emirveliyev/tg-education-helper-bot.git
cd tg-education-helper-bot
python -m venv venv
source venv/bin/activate   # Linux/Mac
venv\Scripts\activate      # Windows Powershell
cp .env.example .env       # Укажите TELEGRAM_API_TOKEN и ключи
pip install -r requirements.txt
python main.py
```

---

## Переменные окружения
В файле **.env** должны быть заданы:  
```
TELEGRAM_API_TOKEN=токен_бота
ADMIN=ид_админа

GEMINI_API_KEY=ключ-гуглапи
API_BASE=ur
GEMINI_MODEL=модель

MAX_OUTPUT_TOKENS=5000 
TEMPERATURE=0.8
DB_PATH=data/bot_data.sqlite3
```

---

## Структура данных
- Пользователи сохраняются в `users.json` (ID, имя, телефон, дата регистрации, согласие).  
- Сгенерированные тесты сохраняются как файлы `tests_{uid}_{timestamp}.json`.  

---

## Лицензия
MIT — см. [LICENSE](./LICENSE)