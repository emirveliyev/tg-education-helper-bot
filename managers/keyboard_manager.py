from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

class KeyboardManager:
    @staticmethod
    def inline(rows: list[tuple[str, str]], row_width: int = 1) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=row_width)
        for text, callback_data in rows:
            kb.add(InlineKeyboardButton(text, callback_data=callback_data))
        return kb

    @staticmethod
    def get_main_kb(user_accepted: bool) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=1)
        if not user_accepted:
            kb.add(InlineKeyboardButton("📱 Поделиться номером для регистрации",
                                    callback_data="request_contact_cb")
                                    )
        kb.add(InlineKeyboardButton("🧠 Сгенерировать тесты", 
                                    callback_data="start_gen_cb")
                                    )
        kb.add(InlineKeyboardButton("🔍 Поиск в Википедии", 
                                    callback_data="wiki_start_cb")
                                    )
        kb.add(InlineKeyboardButton("✏️ Изменить вопросы (СОР/СОЧ)", 
                                    callback_data="modify_start_cb")
                                    )
        kb.add(InlineKeyboardButton("❓ Помощь и информация", 
                                    callback_data="help_cb")
                                    )
        return kb

    @staticmethod
    def get_language_kb() -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=3)
        kb.add(
            InlineKeyboardButton("🇷🇺 Русский", 
                                 callback_data="lang:Русский"),
            InlineKeyboardButton("🇬🇧 Английский", 
                                 callback_data="lang:English"),
            InlineKeyboardButton("🇺🇿 Узбекский", 
                                 callback_data="lang:Uzbek")
        )
        return kb

    @staticmethod
    def get_count_kb() -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=5)
        kb.add(
            InlineKeyboardButton("5", 
                                 callback_data="count:5"),
            InlineKeyboardButton("10", 
                                 callback_data="count:10"),
            InlineKeyboardButton("15", 
                                 callback_data="count:15"),
            InlineKeyboardButton("20 [СКОРО]", 
                                 callback_data="count:20"),
            InlineKeyboardButton("30 [СКОРО]", 
                                 callback_data="count:30")
        )
        return kb

    @staticmethod
    def get_question_type_kb() -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("🔒 Закрытые (варианты a-d)", 
                                 callback_data="qtype:closed"),
            InlineKeyboardButton("📝 Открытые (краткий ответ)", 
                                 callback_data="qtype:open")
        )
        return kb

    @staticmethod
    def get_cancel_kb() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup().add(InlineKeyboardButton("❌ Отмена", callback_data="cancel_cb"))