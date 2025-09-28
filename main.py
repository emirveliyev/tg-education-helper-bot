import os
import logging
from dotenv import load_dotenv
from aiogram import executor
from db import init_db

load_dotenv()

from config.config import (
    TELEGRAM_API_TOKEN,
    GEMINI_API_KEY,
    API_BASE,
    GEMINI_MODEL,
    MAX_OUTPUT_TOKENS,
    TEMPERATURE,
    ADMIN,
)
from core.bot import bot, dp
from handlers.common_handlers import register_common_handlers
from handlers.gen_handlers import register_gen_handlers
from handlers.wiki_handlers import register_wiki_handlers
from handlers.modify_handlers import register_modify_handlers
from handlers.admin_handlers import register_admin_handlers
from utils.utils import on_shutdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("tg-edu-bot")

if not TELEGRAM_API_TOKEN:
    logger.critical("TELEGRAM_API_TOKEN не найден.")
    exit(1)

def register_all_handlers(dp):
    """Регистрация всех хендлеров"""
    register_common_handlers(dp)
    register_gen_handlers(dp)
    register_wiki_handlers(dp)
    register_modify_handlers(dp)
    register_admin_handlers(dp)


if __name__ == "__main__":
    try:
        logger.info("Бот запущен и работает.")
        init_db()
        register_all_handlers(dp)
        executor.start_polling(
            dp,
            skip_updates=True,
            on_shutdown=on_shutdown,
        )
    except Exception as e:
        logger.exception(f"ошибка при запуске бота: {e}")
    finally:
        logger.info("Работа бота завершена")