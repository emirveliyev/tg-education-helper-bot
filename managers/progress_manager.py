from core.bot import bot
import logging

logger = logging.getLogger("tg-edu-bot")

class ProgressManager:
    @staticmethod
    def progress_bar(percent: int, length: int = 20) -> str:
        filled = int(length * percent / 100)
        bar = "█" * filled + "░" * (length - filled)
        return f"{bar} {percent}%"

    @staticmethod
    async def safe_edit_progress(chat_id: int, message_id: int, percent: int,
                                 message_prefix: str, emoji: str = "⏳") -> bool:
        try:
            text = f"{emoji} {message_prefix}\n{ProgressManager.progress_bar(percent)}"
            await bot.edit_message_text(text, chat_id, message_id)
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления прогресса: {e}")
            return False