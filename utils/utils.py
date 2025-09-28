import os
import aiohttp
import asyncio
import logging
import tempfile
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Dict, Optional

logger = logging.getLogger("tg-edu-bot")

HTTP_CONNECTOR_LIMIT = 40
_global_aiohttp_session: Optional[aiohttp.ClientSession] = None
GEMINI_SEMAPHORE = asyncio.Semaphore(3)

pending_contacts: Dict[int, Dict] = {}
user_exports: Dict[int, Dict] = {}
wiki_sessions: Dict[int, Dict] = {}
modify_sessions: Dict[int, Dict] = {}


def get_aiohttp_session() -> aiohttp.ClientSession:
    global _global_aiohttp_session
    try:
        if _global_aiohttp_session is None or _global_aiohttp_session.closed:
            connector = aiohttp.TCPConnector(limit=HTTP_CONNECTOR_LIMIT, limit_per_host=10)
            timeout = aiohttp.ClientTimeout(total=120)
            _global_aiohttp_session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        return _global_aiohttp_session
    except RuntimeError as e:
        logger.warning("RuntimeError при создании aiohttp session: %s — пробуем ещё раз", e)
        connector = aiohttp.TCPConnector(limit=HTTP_CONNECTOR_LIMIT, limit_per_host=10)
        timeout = aiohttp.ClientTimeout(total=120)
        _global_aiohttp_session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        return _global_aiohttp_session


@asynccontextmanager
async def safe_state_transaction(state):
    try:
        yield
    except Exception as e:
        try:
            logger.error("Ошибка в состоянии FSM: %s", e, exc_info=True)
            if state is not None:
                await state.finish()
        except Exception:
            logger.exception("Не удалось корректно завершить состояние FSM после ошибки.")


class SessionManager:
    @staticmethod
    def cleanup_old_sessions(ttl_seconds: int = 3600) -> None:
        current_time = datetime.utcnow()
        global pending_contacts
        cleaned = {}
        for k, v in pending_contacts.items():
            created_at = v.get("created_at")
            try:
                created_dt = datetime.fromisoformat(created_at) if created_at else current_time
            except Exception:
                created_dt = current_time
            if (current_time - created_dt).total_seconds() < ttl_seconds:
                cleaned[k] = v
        pending_contacts = cleaned

    @staticmethod
    async def periodic_cleanup(interval_seconds: int = 600, ttl_seconds: int = 3600):
        try:
            while True:
                SessionManager.cleanup_old_sessions(ttl_seconds=ttl_seconds)
                await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("Periodic cleanup task cancelled")
        except Exception:
            logger.exception("Ошибка в периодической очистке сессий")


async def on_shutdown(dp):
    logger.info("Завершение работы бота...")
    global _global_aiohttp_session
    try:
        if _global_aiohttp_session and not _global_aiohttp_session.closed:
            await _global_aiohttp_session.close()
            logger.info("aiohttp session закрыт")
    except Exception:
        logger.exception("Ошибка при закрытии aiohttp session")
    logger.info("Бот успешно остановлен")


def get_directory_size(path: str) -> int:
    total_size = 0
    if not os.path.exists(path):
        return 0
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            try:
                if os.path.isfile(filepath):
                    total_size += os.path.getsize(filepath)
            except Exception:
                logger.debug("Не удалось получить размер файла: %s", filepath, exc_info=True)
    return total_size