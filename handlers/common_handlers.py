from datetime import datetime
import logging

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from core.bot import bot, dp
from database.database_manager import DatabaseManager
from managers.keyboard_manager import KeyboardManager
from utils.utils import pending_contacts, safe_state_transaction
from config.config import ADMIN

logger = logging.getLogger(__name__)

def register_common_handlers(dp: Dispatcher):
    dp.register_message_handler(cmd_start, commands=["start"])
    dp.register_callback_query_handler(cb_help, lambda c: c.data == "help_cb")
    dp.register_callback_query_handler(cb_request_contact, lambda c: c.data == "request_contact_cb")
    dp.register_message_handler(contact_handler, content_types=types.ContentType.CONTACT)
    dp.register_callback_query_handler(cb_accept_privacy, lambda c: c.data and c.data.startswith("accept_privacy:"))
    dp.register_callback_query_handler(cb_decline_privacy, lambda c: c.data and c.data.startswith("decline_privacy:"))
    dp.register_callback_query_handler(cb_cancel, lambda c: c.data == "cancel_cb", state="*")
    dp.register_message_handler(fallback_handler)

async def cmd_start(message: types.Message):
    try:
        user = DatabaseManager.get_user(message.from_user.id)
        accepted = bool(user and user.get("accepted"))
        greeting = (
            f"👋 <b>Добро пожаловать, {message.from_user.full_name or message.from_user.username or 'Пользователь'}!</b>\n\n"
            "Я — умный помощник для учителей и учеников. С моей помощью вы можете:\n"
            "• Генерировать персонализированные тесты по любому предмету и теме.\n"
            "• Искать информацию в Википедии и получать готовые материалы в формате Word.\n"
            "• Модифицировать существующие вопросы (например, для СОР/СОЧ), изменяя тему или переменные, сохраняя логику.\n\n"
            "Для полного доступа зарегистрируйтесь, поделившись номером телефона. Это позволит сохранять историю и экспортировать файлы.\n\n"
            "Начните с кнопок ниже!"
        )
        kb = KeyboardManager.get_main_kb(accepted)
        await message.answer(greeting, reply_markup=kb)
    except Exception as e:
        logger.exception("Ошибка в команде /start")
        await message.answer("Произошла ошибка. Попробуйте позже.")

async def cb_help(query: types.CallbackQuery):
    await query.answer()
    try:
        text = (
            "📚 <b>Руководство по использованию бота</b>\n\n"
            "Этот бот предназначен для упрощения подготовки образовательных материалов. Вот подробное описание функций:\n\n"
            "1. <b>Генерация тестов [ПОПУЛЯРНО]</b>:\n"
            "   - Выберите предмет, тему, класс, количество вопросов, язык и тип (закрытые с вариантами или открытые).\n"
            "   - Бот создаст тесты с помощью ИИ, предоставит их в чате и в формате Word (для учеников и с ответами для учителя).\n"
            "   - Полезно для: контрольных работ, домашних заданий, викторин.\n\n"
            "2. <b>Поиск в Википедии [БЕТА ВЕРСИЯ]</b>:\n"
            "   - Введите запрос — бот найдет релевантную статью, извлечет ключевую информацию.\n"
            "   - Получите готовый документ Word с текстом для уроков или презентаций.\n"
            "   - Совет: Укажите точный запрос для лучших результатов.\n\n"
            "3. <b>Модификация вопросов [БЕТА ВЕРСИЯ]</b>:\n"
            "   - Отправьте существующие вопросы и ответы.\n"
            "   - Выберите режим: изменить тему (сохранить решения) или переменные (изменить числа).\n"
            "   - Получите новые варианты в Word — идеально для создания альтернативных тестов без плагиата.\n\n"
            "Если возникнут проблемы, обратитесь к администратору. Наслаждайтесь использованием! 🚀"
        )
        user = DatabaseManager.get_user(query.from_user.id)
        user_accepted = bool(user and user.get("accepted"))
        await bot.send_message(query.from_user.id, text, reply_markup=KeyboardManager.get_main_kb(user_accepted))
    except Exception as e:
        logger.exception("Ошибка в cb_help")
        await query.answer("Произошла ошибка. Попробуйте позже.", show_alert=True)

async def cb_request_contact(query: types.CallbackQuery):
    await query.answer()
    try:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(types.KeyboardButton("📞 Отправить мой контакт", request_contact=True))
        await bot.send_message(
            query.from_user.id,
            "Для регистрации нажмите кнопку ниже и поделитесь номером телефона. Это позволит использовать все функции бота.",
            reply_markup=kb
        )
    except Exception as e:
        logger.exception("Ошибка в cb_request_contact")
        await query.answer("Произошла ошибка. Попробуйте позже.", show_alert=True)

async def contact_handler(message: types.Message):
    try:
        contact = message.contact
        if not contact:
            await message.answer("Контакт не распознан. Попробуйте заново через меню.")
            return
        if contact.user_id != message.from_user.id:
            await message.answer("Пожалуйста, отправьте только свой контакт.")
            return
        pending_contacts[message.from_user.id] = {
            "phone": contact.phone_number,
            "username": message.from_user.username or "",
            "created_at": datetime.utcnow().isoformat()
        }
        privacy_text = (
            "📜 <b>Политика конфиденциальности и условия использования</b>\n\n"
            "Регистрируясь, вы соглашаетесь с хранением вашего номера телефона для управления аккаунтом, "
            "историей генераций и уведомлений. Мы не передаем данные третьим лицам и используем их только "
            "для улучшения сервиса. Вы можете удалить аккаунт в любое время, обратившись к администратору.\n\n"
            "Принять условия?"
        )
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("✅ Принять и зарегистрироваться", callback_data=f"accept_privacy:{message.from_user.id}"))
        kb.add(InlineKeyboardButton("❌ Отклонить", callback_data=f"decline_privacy:{message.from_user.id}"))
        await message.answer(privacy_text, reply_markup=kb)
    except Exception as e:
        logger.exception("Ошибка обработки контакта")
        await message.answer("Произошла ошибка при обработке контакта. Попробуйте позже.")

async def cb_accept_privacy(query: types.CallbackQuery):
    await query.answer()
    try:
        uid = int(query.data.split(":", 1)[1])
        if uid != query.from_user.id:
            await query.answer("Эта кнопка предназначена только для вас.", show_alert=True)
            return
        pending = pending_contacts.get(uid)
        if not pending:
            await query.answer("Данные контакта не найдены. Отправьте контакт заново.", show_alert=True)
            return
        DatabaseManager.add_or_update_user(
            uid,
            pending.get("username", ""),
            pending.get("phone", ""),
            accepted=True
        )
        pending_contacts.pop(uid, None)
        await bot.send_message(
            uid,
            "✅ Регистрация успешно завершена! Теперь вы имеете полный доступ ко всем функциям бота, включая генерацию и экспорт тестов.",
            reply_markup=KeyboardManager.get_main_kb(True)
        )
    except ValueError:
        await query.answer("Ошибка регистрации. Попробуйте заново.", show_alert=True)
    except Exception as e:
        logger.exception("Ошибка принятия политики")
        await query.answer("Произошла ошибка. Попробуйте позже.", show_alert=True)

async def cb_decline_privacy(query: types.CallbackQuery):
    await query.answer()
    try:
        uid = int(query.data.split(":", 1)[1])
        if uid != query.from_user.id:
            await query.answer("Эта кнопка предназначена только для вас.", show_alert=True)
            return
        pending_contacts.pop(uid, None)
        await bot.send_message(
            uid,
            "Регистрация отменена. Вы можете зарегистрироваться позже через меню.",
            reply_markup=KeyboardManager.get_main_kb(False)
        )
    except Exception as e:
        logger.exception("Ошибка отклонения политики")

async def cb_cancel(query: types.CallbackQuery, state: FSMContext):
    await query.answer()
    try:
        async with safe_state_transaction(state):
            await state.finish()
            user = DatabaseManager.get_user(query.from_user.id)
            user_accepted = bool(user and user.get("accepted"))
            await bot.send_message(
                query.from_user.id,
                "Операция отменена. Вы возвращены в главное меню.",
                reply_markup=KeyboardManager.get_main_kb(user_accepted)
            )
    except Exception as e:
        logger.exception("Ошибка отмены операции")
        await query.answer("Произошла ошибка. Попробуйте позже.", show_alert=True)

async def fallback_handler(message: types.Message):
    try:
        user = DatabaseManager.get_user(message.from_user.id)
        user_accepted = bool(user and user.get("accepted"))
        await message.answer(
            "Я не понял ваш запрос. Используйте кнопки в меню или команду /start для начала работы.",
            reply_markup=KeyboardManager.get_main_kb(user_accepted)
        )
    except Exception as e:
        logger.exception("Ошибка в fallback_handler")
        await message.answer("Произошла ошибка. Попробуйте позже.")