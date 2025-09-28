from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext

import os
import asyncio
from datetime import datetime
import logging
from typing import List

from core.bot import bot, dp
from states.states import WikiStates
from database.database_manager import DatabaseManager
from managers.keyboard_manager import KeyboardManager
from managers.progress_manager import ProgressManager
from managers.wikipedia_manager import WikipediaManager
from api.gemini_api import GeminiAPI
from api.image_generator import ImageGenerator
from api.document_generator import DocumentGenerator
from utils.utils import wiki_sessions, safe_state_transaction
from config.config import DATA_DIR

logger = logging.getLogger("tg-edu-bot")


def register_wiki_handlers(dp: Dispatcher):
    dp.register_callback_query_handler(cb_wiki_start, lambda c: c.data == "wiki_start_cb")
    dp.register_message_handler(wiki_query_handler, state=WikiStates.query)
    dp.register_callback_query_handler(wiki_page_cb, lambda c: c.data and c.data.startswith("wiki_page:"), state=WikiStates.pick)
    dp.register_callback_query_handler(wiki_pick_cb, lambda c: c.data and c.data.startswith("wiki_pick:"), state=WikiStates.pick)


async def cb_wiki_start(query: types.CallbackQuery):
    await query.answer()

    await bot.send_message(
        query.from_user.id,
        "🔍 Введите запрос для поиска в Википедии (например, 'Теорема Пифагора' или 'Photosynthesis'). "
        "Для отмены отправьте 'Отмена'.",
        reply_markup=KeyboardManager.get_cancel_kb()
    )
    await WikiStates.query.set()


async def wiki_query_handler(message: types.Message, state: FSMContext):
    text = GeminiAPI.sanitize_text(message.text)

    if text.lower() == "отмена":
        await state.finish()
        user_accepted = bool(DatabaseManager.get_user(message.from_user.id))
        await message.answer("Поиск отменен.", reply_markup=KeyboardManager.get_main_kb(user_accepted))
        return

    progress_msg = await message.answer(f"⏳ Поиск в Википедии... {ProgressManager.progress_bar(0)}")

    try:
        await ProgressManager.safe_edit_progress(
            message.chat.id, progress_msg.message_id, 20,
            "🔎 Ищу релевантные статьи...", "🔍"
        )

        results = await WikipediaManager.search(text, "ru", 20)

        if not results:
            await ProgressManager.safe_edit_progress(
                message.chat.id, progress_msg.message_id, 100,
                "❗ Ничего не найдено. Попробуйте уточнить запрос.", "❌"
            )
            await bot.send_message(
                message.from_user.id,
                "Нет результатов. Измените запрос или попробуйте на другом языке.",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("🔄 Попробовать заново", callback_data="wiki_start_cb")
                )
            )
            await state.finish()
            return

        wiki_sessions[message.from_user.id] = {
            "query": text,
            "lang": "ru",
            "results": results,
            "progress_msg_id": progress_msg.message_id
        }

        if len(results) == 1:
            await process_wiki_result(message.from_user.id, results[0], progress_msg.message_id, state)
        else:
            await show_wiki_results(progress_msg.message_id, message.chat.id, results, 0, "ru")
            await WikiStates.pick.set()

    except Exception as e:
        logger.exception("Ошибка поиска Wikipedia: %s", e)
        try:
            await ProgressManager.safe_edit_progress(
                message.chat.id, progress_msg.message_id, 0,
                "❗ Ошибка поиска.", "❌"
            )
        except Exception:
            logger.exception("Не удалось обновить прогресс при ошибке поиска.")
        await bot.send_message(message.from_user.id, "Произошла ошибка. Попробуйте позже.")


async def process_wiki_result(user_id: int, title: str, progress_msg_id: int, state: FSMContext):
    try:
        await ProgressManager.safe_edit_progress(
            user_id, progress_msg_id, 30,
            "📄 Получаю содержимое страницы...", "📄"
        )

        page = await WikipediaManager.get_page(title, "ru")
        if not page:
            await ProgressManager.safe_edit_progress(
                user_id, progress_msg_id, 100,
                "❗ Не удалось получить страницу.", "❌"
            )
            await bot.send_message(
                user_id,
                "Ошибка получения данных. Попробуйте другой запрос.",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("🔄 Попробовать заново", callback_data="wiki_start_cb")
                )
            )
            await state.finish()
            return

        await ProgressManager.safe_edit_progress(
            user_id, progress_msg_id, 50,
            "📝 Улучшаю текст через Gemini...", "📝"
        )

        improved_content = await GeminiAPI.call_gemini_for_text_improvement(
            page.get("content", ""), "ru"
        )

        await ProgressManager.safe_edit_progress(
            user_id, progress_msg_id, 70,
            "🖼 Скачиваю изображения...", "🖼"
        )

        images_bytes = []
        for img_url in (page.get("images") or [])[:3]:
            try:
                img_buffer = await WikipediaManager.download_image(img_url)
                if img_buffer:
                    images_bytes.append(img_buffer)
            except Exception as e:
                logger.warning("Не удалось скачать изображение %s: %s", img_url, e)

        await ProgressManager.safe_edit_progress(
            user_id, progress_msg_id, 80,
            "📝 Создаю документ Word...", "📝"
        )

        try:
            header_buf = await asyncio.to_thread(
                ImageGenerator.make_header_image,
                page["title"],
                "Из Википедии",
                username=str(user_id)
            )
        except Exception as e:
            logger.exception("Ошибка при создании header image: %s", e)
            header_buf = None

        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_out_dir = os.path.abspath(DATA_DIR)
        os.makedirs(safe_out_dir, exist_ok=True)
        out_path = os.path.join(safe_out_dir, f"wiki_{user_id}_{ts}.docx")

        try:
            created = await asyncio.to_thread(
                DocumentGenerator.create_docx_file,
                {
                    "subject": "",
                    "topic": page["title"],
                    "grade": "",
                    "language": "ru",
                    "user_id": user_id
                },
                [],
                header_buf,
                out_path,
                False,
                "open",
                images_bytes,
                improved_content
            )
        except Exception as e:
            logger.exception("Ошибка при создании документа: %s", e)
            created = False

        if created:
            try:
                with open(out_path, "rb") as f:
                    await bot.send_document(
                        user_id,
                        types.InputFile(f, filename=f"Википедия_{page['title']}_{ts}.docx"),
                        caption=f"📘 Результат поиска: '{page['title']}'. Документ готов!"
                    )
            except Exception as e:
                logger.exception("Ошибка отправки документа: %s", e)
                await bot.send_message(user_id, "Документ создан, но возникла ошибка при отправке.")
        else:
            await bot.send_message(user_id, "Не удалось создать документ. Попробуйте позже.")

        await ProgressManager.safe_edit_progress(
            user_id, progress_msg_id, 100,
            "✅ Поиск завершен!", "🎉"
        )

    except Exception as e:
        logger.exception("Ошибка обработки результата Wikipedia: %s", e)
        try:
            await ProgressManager.safe_edit_progress(
                user_id, progress_msg_id, 0,
                "❗ Ошибка обработки.", "❌"
            )
        except Exception:
            logger.exception("Не удалось обновить прогресс при обработке ошибки.")
    finally:
        try:
            await state.finish()
        except Exception:
            logger.exception("Не удалось завершить состояние FSM.")
        wiki_sessions.pop(user_id, None)


async def show_wiki_results(message_id: int, chat_id: int, results: List[str], page: int, lang: str):
    per_page = 6
    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_results = results[start_idx:end_idx]

    if not page_results:
        return

    kb = types.InlineKeyboardMarkup(row_width=1)

    for idx, title in enumerate(page_results):
        global_idx = start_idx + idx
        kb.add(types.InlineKeyboardButton(title, callback_data=f"wiki_pick:{global_idx}"))

    nav_buttons = []
    if page > 0:
        nav_buttons.append(types.InlineKeyboardButton("◀️ Предыдущая", callback_data=f"wiki_page:{page-1}"))

    if end_idx < len(results):
        nav_buttons.append(types.InlineKeyboardButton("Следующая ▶️", callback_data=f"wiki_page:{page+1}"))

    if nav_buttons:
        kb.row(*nav_buttons)

    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_cb"))

    text = f"🔎 Найдено несколько вариантов (страница {page+1}):"
    try:
        await bot.edit_message_text(text, chat_id, message_id, reply_markup=kb)
    except Exception as e:
        logger.exception("Не удалось отредактировать сообщение с результатами: %s", e)


async def wiki_page_cb(query: types.CallbackQuery, state: FSMContext):
    await query.answer()

    try:
        page = int(query.data.split(":", 1)[1])
        session = wiki_sessions.get(query.from_user.id, {})
        results = session.get("results", [])
        lang = session.get("lang", "ru")

        if not results:
            await query.answer("Сессия устарела.", show_alert=True)
            await state.finish()
            return

        await show_wiki_results(query.message.message_id, query.from_user.id, results, page, lang)

    except ValueError:
        await query.answer("Ошибка пагинации.", show_alert=True)


async def wiki_pick_cb(query: types.CallbackQuery, state: FSMContext):
    await query.answer()

    try:
        idx = int(query.data.split(":", 1)[1])
        session = wiki_sessions.get(query.from_user.id, {})
        results = session.get("results", [])

        if idx < 0 or idx >= len(results):
            await query.answer("Неверный выбор.", show_alert=True)
            return

        title = results[idx]
        progress_msg = await bot.send_message(
            query.from_user.id,
            f"⏳ Получаю '{title}'... {ProgressManager.progress_bar(0)}"
        )

        await process_wiki_result(query.from_user.id, title, progress_msg.message_id, state)

    except Exception as e:
        logger.exception("Ошибка выбора Wikipedia: %s", e)
        await query.answer("Произошла ошибка.", show_alert=True)