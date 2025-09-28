import os
import json
import threading
import tempfile
import shutil
import logging
from datetime import datetime
from typing import Dict, List, Optional

from config.config import DATA_DIR

logger = logging.getLogger(__name__)
_user_file_lock = threading.Lock()

class DatabaseManager:
    @staticmethod
    def init() -> None:
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
        except Exception as e:
            logger.exception("Не удалось создать папку DATA_DIR %s: %s", DATA_DIR, e)
            raise

    @staticmethod
    def get_users_file_path() -> str:
        DatabaseManager.init()
        return os.path.join(DATA_DIR, "users.json")

    @staticmethod
    def _read_users() -> Dict[str, Dict]:
        path = DatabaseManager.get_users_file_path()
        try:
            with _user_file_lock:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
                    logger.warning("Файл пользователей не в формате dict — верну пустой словарь.")
                    return {}
        except FileNotFoundError:
            logger.info("Файл пользователей не найден: %s. Верну пустой словарь.", path)
            return {}
        except json.JSONDecodeError:
            logger.exception("Ошибка разбора JSON в файле пользователей; верну пустой словарь.")
            return {}
        except Exception as e:
            logger.exception("Неожиданная ошибка при чтении файла пользователей: %s", e)
            return {}

    @staticmethod
    def _write_users(users: Dict[str, Dict]) -> None:
        path = DatabaseManager.get_users_file_path()
        dirpath = os.path.dirname(path)
        os.makedirs(dirpath, exist_ok=True)
        tmp_fd = None
        tmp_path = None
        try:
            with _user_file_lock:
                tmp_fd, tmp_path = tempfile.mkstemp(prefix="users_", dir=dirpath, text=True)
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(users, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                shutil.move(tmp_path, path)
        except Exception as e:
            logger.exception("Ошибка при записи файла пользователей: %s", e)
            try:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                logger.exception("Не смог удалить временный файл пользователей.")
            raise

    @staticmethod
    def add_or_update_user(uid: int, username: str, phone: str, accepted: bool = False) -> None:
        if not isinstance(uid, int):
            raise ValueError("uid должен быть int")
        users = DatabaseManager._read_users()
        key = str(uid)
        now = datetime.utcnow().isoformat()
        existing = users.get(key)
        if existing:
            existing["username"] = username or existing.get("username", "")
            existing["phone"] = phone or existing.get("phone", "")
            existing["accepted"] = bool(accepted) or existing.get("accepted", False)
            existing["updated_at"] = now
            users[key] = existing
            logger.info("Обновлен пользователь %s", uid)
        else:
            users[key] = {
                "id": uid,
                "username": username or "",
                "phone": phone or "",
                "accepted": bool(accepted),
                "registered_at": now,
                "updated_at": None
            }
            logger.info("Добавлен новый пользователь %s", uid)
        DatabaseManager._write_users(users)

    @staticmethod
    def get_user(uid: int) -> Optional[Dict]:
        if not isinstance(uid, int):
            logger.warning("get_user: uid не int")
            return None
        users = DatabaseManager._read_users()
        user = users.get(str(uid))
        if user:
            logger.debug("Найден пользователь %s", uid)
            return user
        logger.info("Пользователь %s не найден", uid)
        return None

    @staticmethod
    def list_users() -> List[Dict]:
        users = DatabaseManager._read_users()
        return list(users.values())

    @staticmethod
    def user_exists(uid: int) -> bool:
        return DatabaseManager.get_user(uid) is not None

    @staticmethod
    def set_accepted(uid: int, accepted: bool = True) -> bool:
        if not isinstance(uid, int):
            logger.warning("set_accepted: uid не int")
            return False
        users = DatabaseManager._read_users()
        key = str(uid)
        if key not in users:
            logger.info("set_accepted: пользователь %s не найден", uid)
            return False
        users[key]["accepted"] = bool(accepted)
        users[key]["updated_at"] = datetime.utcnow().isoformat()
        DatabaseManager._write_users(users)
        logger.info("Пользователь %s помечен accepted=%s", uid, accepted)
        return True

    @staticmethod
    def update_user_phone(uid: int, phone: str) -> bool:
        if not isinstance(uid, int):
            logger.warning("update_user_phone: uid не int")
            return False
        users = DatabaseManager._read_users()
        key = str(uid)
        if key not in users:
            logger.info("update_user_phone: пользователь %s не найден", uid)
            return False
        users[key]["phone"] = phone
        users[key]["updated_at"] = datetime.utcnow().isoformat()
        DatabaseManager._write_users(users)
        logger.info("У пользователя %s обновлён телефон", uid)
        return True

    @staticmethod
    def remove_user(uid: int) -> bool:
        if not isinstance(uid, int):
            logger.warning("remove_user: uid не int")
            return False
        users = DatabaseManager._read_users()
        key = str(uid)
        if key in users:
            users.pop(key)
            DatabaseManager._write_users(users)
            logger.info("Пользователь %s удалён", uid)
            return True
        logger.info("remove_user: пользователь %s не найден", uid)
        return False

    @staticmethod
    def get_or_create_user(uid: int, username: str = "", phone: str = "", accepted: bool = False) -> Dict:
        if not isinstance(uid, int):
            raise ValueError("uid должен быть int")
        users = DatabaseManager._read_users()
        key = str(uid)
        if key in users:
            logger.debug("get_or_create_user: возвращаю существующего %s", uid)
            return users[key]
        now = datetime.utcnow().isoformat()
        users[key] = {
            "id": uid,
            "username": username or "",
            "phone": phone or "",
            "accepted": bool(accepted),
            "registered_at": now,
            "updated_at": None
        }
        DatabaseManager._write_users(users)
        logger.info("get_or_create_user: создан новый пользователь %s", uid)
        return users[key]

    @staticmethod
    def save_test(uid: int, meta: Dict, tests: List) -> str:
        DatabaseManager.init()
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_uid = int(uid) if isinstance(uid, int) else 0
        file_name = f"tests_{safe_uid}_{ts}.json"
        file_path = os.path.join(DATA_DIR, file_name)
        test_data = {
            "meta": meta,
            "tests": tests,
            "created_at": datetime.utcnow().isoformat()
        }
        try:
            dirpath = os.path.dirname(file_path)
            os.makedirs(dirpath, exist_ok=True)
            tmp_fd, tmp_path = tempfile.mkstemp(prefix="tests_", dir=dirpath, text=True)
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(test_data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            shutil.move(tmp_path, file_path)
            logger.info("Тест сохранён в файл %s", file_path)
            return file_path
        except Exception as e:
            logger.exception("Не удалось сохранить тест в файл %s: %s", file_path, e)
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(test_data, f, ensure_ascii=False, indent=2)
                logger.info("Тест сохранён через fallback в %s", file_path)
                return file_path
            except Exception as e2:
                logger.exception("Альтернативная запись также не удалась: %s", e2)
                raise