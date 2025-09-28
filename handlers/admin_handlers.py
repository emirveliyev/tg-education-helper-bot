import os
import asyncio
import logging
from datetime import datetime
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext

from core.bot import bot, dp
from states.states import AdminStates
from database.database_manager import DatabaseManager
from utils.utils import get_directory_size
from config.config import DATA_DIR, ADMIN

logger = logging.getLogger("tg-edu-bot")

def register_admin_handlers(dp: Dispatcher):
    dp.register_message_handler(cmd_list_users, commands=["users"])
    dp.register_message_handler(cmd_stats, commands=["stats"])
    dp.register_message_handler(cmd_broadcast, commands=["broadcast"])
    dp.register_callback_query_handler(admin_callbacks, lambda c: c.data and c.data.startswith("admin:"))
    dp.register_message_handler(admin_broadcast_text, state=AdminStates.broadcast_text)
    dp.register_message_handler(admin_broadcast_photo, content_types=types.ContentType.PHOTO, state=AdminStates.broadcast_photo)

async def cmd_list_users(message: types.Message):
    if message.from_user.id != ADMIN:
        await message.answer("Доступ запрещен.")
        return

    users = DatabaseManager.list_users()
    if not users:
        await message.answer("Список пользователей пуст.")
        return

    lines = []
    for user in users:
        user_id = user.get('id', 'N/A')
        username = user.get('username', 'Нет')
        phone = user.get('phone', 'Нет')
        accepted = user.get('accepted', False)
        registered = user.get('registered_at', 'Неизвестно')

        lines.append(f"{user_id} | @{username} | {phone} | Принял: {accepted} | {registered}")

    text = "<b>Список пользователей:</b>\n\n" + "\n".join(lines)

    if len(text) <= 4000:
        await message.answer(text)
    else:
        filename = os.path.join(DATA_DIR, f"users_list_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.txt")
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        with open(filename, "rb") as f:
            await bot.send_document(
                message.from_user.id,
                types.InputFile(f, filename=os.path.basename(filename)),
                caption="Полный список пользователей"
            )
        os.remove(filename)

async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN:
        await message.answer("Доступ запрещен.")
        return

    users = DatabaseManager.list_users()
    total_users = len(users)
    accepted_users = len([u for u in users if u.get('accepted')])

    test_files = [f for f in os.listdir(DATA_DIR) if f.startswith('tests_') and f.endswith('.json')]

    text = (
        f"<b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: <b>{total_users}</b>\n"
        f"✅ Зарегистрированных: <b>{accepted_users}</b>\n"
        f"📊 Файлов тестов: <b>{len(test_files)}</b>\n"
        f"💾 Размер данных: <b>{get_directory_size(DATA_DIR) / 1024 / 1024:.2f} MB</b>"
    )

    await message.answer(text)

async def cmd_broadcast(message: types.Message):
    if message.from_user.id != ADMIN:
        await message.answer("Доступ запрещен.")
        return

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📢 Текстовая рассылка", callback_data="admin:broadcast_text"))
    kb.add(types.InlineKeyboardButton("🖼 Рассылка с фото", callback_data="admin:broadcast_photo"))

    await message.answer(
        "Выберите тип рассылки:",
        reply_markup=kb
    )

async def admin_callbacks(query: types.CallbackQuery):
    await query.answer()

    if query.from_user.id != ADMIN:
        await query.answer("Доступ запрещен.", show_alert=True)
        return

    command = query.data.split(":", 1)[1]

    if command == "broadcast_text":
        await bot.send_message(
            query.from_user.id,
            "Введите текст для рассылки всем пользователям. Для отмены отправьте 'Отмена'."
        )
        await AdminStates.broadcast_text.set()

    elif command == "broadcast_photo":
        await bot.send_message(
            query.from_user.id,
            "Отправьте фото с подписью для рассылки. Для отмены отправьте 'Отмена'."
        )
        await AdminStates.broadcast_photo.set()

async def admin_broadcast_text(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN:
        await message.answer("Доступ запрещен.")
        await state.finish()
        return

    text = message.text.strip()
    if text.lower() == "отмена":
        await state.finish()
        await message.answer("Доступ запрещен.")
        return

    users = DatabaseManager.list_users()
    total_sent = 0
    failed = 0

    progress_msg = await message.answer(f"📢 Начинаю рассылку... 0/{len(users)}")

    for i, user in enumerate(users):
        user_id = user.get('id')
        if not user_id:
            continue

        try:
            await bot.send_message(user_id, text)
            total_sent += 1

            if i % 10 == 0:
                await bot.edit_message_text(
                    f"📢 Рассылка... {i+1}/{len(users)}",
                    message.chat.id,
                    progress_msg.message_id
                )

            await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"Ошибка рассылки пользователю {user_id}: {e}")
            failed += 1

    await bot.edit_message_text(
        f"✅ Рассылка завершена!\nУспешно: {total_sent}\nОшибок: {failed}",
        message.chat.id,
        progress_msg.message_id
    )

    await state.finish()

async def admin_broadcast_photo(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN:
        await message.answer("Доступ запрещен.")
        await state.finish()
        return

    if message.caption and message.caption.strip().lower() == "отмена":
        await state.finish()
        await message.answer("Рассылка отменена.")
        return

    photo = message.photo[-1].file_id
    caption = message.caption or ""

    users = DatabaseManager.list_users()
    total_sent = 0
    failed = 0

    progress_msg = await message.answer(f"🖼 Начинаю рассылку фото... 0/{len(users)}")

    for i, user in enumerate(users):
        user_id = user.get('id')
        if not user_id:
            continue

        try:
            await bot.send_photo(user_id, photo=photo, caption=caption)
            total_sent += 1

            if i % 5 == 0:
                await bot.edit_message_text(
                    f"🖼 Рассылка фото... {i+1}/{len(users)}",
                    message.chat.id,
                    progress_msg.message_id
                )

            await asyncio.sleep(0.2)

        except Exception as e:
            logger.error(f"Ошибка рассылки фото пользователю {user_id}: {e}")
            failed += 1

    await bot.edit_message_text(
        f"✅ Рассылка фото завершена!\nУспешно: {total_sent}\nОшибок: {failed}",
        message.chat.id,
        progress_msg.message_id
    )

    await state.finish()