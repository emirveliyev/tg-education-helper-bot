from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext

import os
import asyncio
from datetime import datetime
import logging
from typing import List

from core.bot import bot, dp
from states.states import ModifyStates
from database.database_manager import DatabaseManager
from api.gemini_api import GeminiAPI
from api.image_generator import ImageGenerator
from api.document_generator import DocumentGenerator
from managers.keyboard_manager import KeyboardManager
from managers.progress_manager import ProgressManager
from utils.utils import modify_sessions
from config.config import DATA_DIR

logger = logging.getLogger("tg-edu-bot")


def register_modify_handlers(dp: Dispatcher):
    dp.register_callback_query_handler(modify_start, lambda c: c.data == "modify_start_cb")
    dp.register_message_handler(modify_collect_q, state=ModifyStates.collecting)
    dp.register_message_handler(modify_collect_answers, state=ModifyStates.answers)
    dp.register_callback_query_handler(modify_choice_cb, lambda c: c.data and c.data.startswith("mod:"), state=ModifyStates.choose_mod)


async def modify_start(query: types.CallbackQuery):
    await query.answer()

    await bot.send_message(
        query.from_user.id,
        "✏️ Режим модификации вопросов запущен. Отправляйте вопросы по одному сообщению. "
        "Когда все вопросы добавлены, отправьте 'Готово'. Для отмены — 'Отмена'.",
        reply_markup=KeyboardManager.get_cancel_kb()
    )

    modify_sessions[query.from_user.id] = {
        "questions": [],
        "answers": [],
        "meta": {"user_id": query.from_user.id}
    }

    await ModifyStates.collecting.set()


async def modify_collect_q(message: types.Message, state: FSMContext):
    text = GeminiAPI.sanitize_text(message.text)

    if text.lower() == "отмена":
        modify_sessions.pop(message.from_user.id, None)
        await state.finish()
        user_accepted = bool(DatabaseManager.get_user(message.from_user.id))
        await message.answer("Модификация отменена.", reply_markup=KeyboardManager.get_main_kb(user_accepted))
        return

    if text.lower() == "готово":
        session = modify_sessions.get(message.from_user.id)
        if not session or not session.get("questions"):
            await message.answer("Вы не добавили вопросы. Отправьте хотя бы один или отмените.")
            return

        await message.answer(
            "Теперь отправьте ответы для каждого вопроса по порядку. Начните с ответа на первый вопрос."
        )
        session["answer_index"] = 0
        await ModifyStates.answers.set()
        return

    session = modify_sessions.get(message.from_user.id)
    if session is None:
        await message.answer("Сессия не активна. Начните заново.")
        await state.finish()
        return

    session["questions"].append(text)
    await message.answer(
        f"✅ Вопрос добавлен. Всего вопросов: {len(session['questions'])}. "
        "Продолжайте добавлять или отправьте 'Готово'."
    )


async def modify_collect_answers(message: types.Message, state: FSMContext):
    text = GeminiAPI.sanitize_text(message.text)

    if text.lower() == "отмена":
        modify_sessions.pop(message.from_user.id, None)
        await state.finish()
        user_accepted = bool(DatabaseManager.get_user(message.from_user.id))
        await message.answer("Модификация отменена.", reply_markup=KeyboardManager.get_main_kb(user_accepted))
        return

    session = modify_sessions.get(message.from_user.id)
    if session is None:
        await state.finish()
        await message.answer("Сессия не активна.")
        return

    idx = session.get("answer_index", 0)
    session["answers"].append(text)
    idx += 1
    session["answer_index"] = idx

    if idx < len(session["questions"]):
        await message.answer(f"Отправьте ответ для вопроса №{idx + 1}:")
        return

    mod_kb = types.InlineKeyboardMarkup(row_width=1)
    mod_kb.add(types.InlineKeyboardButton(
        "🔄 Поменять тему (сохранить логику)",
        callback_data="mod:change_topic"
    ))
    mod_kb.add(types.InlineKeyboardButton(
        "📊 Изменить переменные/числа",
        callback_data="mod:change_variables"
    ))
    mod_kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_cb"))

    await message.answer("Все ответы получены. Выберите режим модификации:", reply_markup=mod_kb)
    await ModifyStates.choose_mod.set()


async def modify_choice_cb(query: types.CallbackQuery, state: FSMContext):
    await query.answer()

    choice = query.data.split(":", 1)[1]
    session = modify_sessions.get(query.from_user.id)

    if not session:
        await bot.send_message(query.from_user.id, "Сессия не найдена.")
        await state.finish()
        return

    progress_msg = await bot.send_message(
        query.from_user.id,
        f"⏳ Генерирую модифицированные вопросы... {ProgressManager.progress_bar(0)}"
    )

    try:
        await ProgressManager.safe_edit_progress(
            query.from_user.id, progress_msg.message_id, 20,
            "🛠 Формирую контекст примеров...", "🚀"
        )

        context_examples = []
        for q, a in zip(session["questions"], session["answers"]):
            context_examples.append({"question": q, "answer": a})

        subject = session.get("meta", {}).get("subject", "Общий")
        topic = session.get("meta", {}).get("topic", "Модификация вопросов")
        grade = session.get("meta", {}).get("grade", "")
        language = "Русский"
        num_questions = len(session["questions"])

        await ProgressManager.safe_edit_progress(
            query.from_user.id, progress_msg.message_id, 40,
            "📡 Отправляю в Gemini AI...", "🚀"
        )

        tests, raw_response = await GeminiAPI.call_gemini(
            subject, topic, grade, language, num_questions,
            qtype="open", context_examples=context_examples,
            modify_mode=choice
        )

        if tests is None:
            await ProgressManager.safe_edit_progress(
                query.from_user.id, progress_msg.message_id, 100,
                "❗ Ошибка генерации.", "❌"
            )
            await bot.send_message(
                query.from_user.id,
                "Не удалось создать модифицированные вопросы. Попробуйте изменить входные данные."
            )
            await state.finish()
            modify_sessions.pop(query.from_user.id, None)
            return

        await ProgressManager.safe_edit_progress(
            query.from_user.id, progress_msg.message_id, 60,
            "📄 Форматирую новые вопросы...", "✅"
        )

        meta = {
            "subject": subject,
            "topic": f"{topic} (модифицировано)",
            "grade": grade,
            "language": language,
            "user_id": query.from_user.id
        }

        # Создание header изображения в фоновом потоке (если тяжёлая синхронная операция)
        try:
            header_buf = await asyncio.to_thread(
                ImageGenerator.make_header_image,
                "Модифицированные вопросы",
                f"Режим: {'Изменение темы' if choice == 'change_topic' else 'Изменение переменных'}",
                username=(query.from_user.username or str(query.from_user.id))
            )
        except Exception as e:
            logger.exception("Ошибка при создании header image: %s", e)
            header_buf = None

        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_out_dir = os.path.abspath(DATA_DIR)
        os.makedirs(safe_out_dir, exist_ok=True)
        base_name = os.path.join(safe_out_dir, f"modified_{query.from_user.id}_{ts}")

        student_docx = base_name + "_student.docx"
        teacher_docx = base_name + "_teacher.docx"

        # Создание документов в фоновом потоке, чтобы не блокировать event loop
        try:
            student_res = await asyncio.to_thread(
                DocumentGenerator.create_docx_file,
                meta, tests, header_buf, student_docx, False, "open"
            )
        except Exception as e:
            logger.exception("Ошибка при создании student doc: %s", e)
            student_res = False

        try:
            teacher_res = await asyncio.to_thread(
                DocumentGenerator.create_docx_file,
                meta, tests, header_buf, teacher_docx, True, "open"
            )
        except Exception as e:
            logger.exception("Ошибка при создании teacher doc: %s", e)
            teacher_res = False

        # Нормализация результатов: DocumentGenerator может возвращать путь или True/False
        def _resolve_path(result, expected_path):
            if isinstance(result, str) and result:
                return result
            if result is True:
                return expected_path
            if result:
                return expected_path
            return None

        student_path = _resolve_path(student_res, student_docx)
        teacher_path = _resolve_path(teacher_res, teacher_docx)

        await ProgressManager.safe_edit_progress(
            query.from_user.id, progress_msg.message_id, 80,
            "📤 Подготавливаю документы к отправке...", "📤"
        )

        if student_path and os.path.exists(student_path) and teacher_path and os.path.exists(teacher_path):
            try:
                with open(student_path, "rb") as f:
                    await bot.send_document(
                        query.from_user.id,
                        types.InputFile(f, filename=os.path.basename(student_path)),
                        caption="📄 Модифицированные вопросы для учеников (без ответов)"
                    )
            except Exception as e:
                logger.exception("Ошибка отправки student doc: %s", e)
                await bot.send_message(query.from_user.id, "Документ для учеников создан, но не удалось отправить его.")

            try:
                with open(teacher_path, "rb") as f:
                    await bot.send_document(
                        query.from_user.id,
                        types.InputFile(f, filename=os.path.basename(teacher_path)),
                        caption="📝 Модифицированные вопросы для учителя (с ответами)"
                    )
            except Exception as e:
                logger.exception("Ошибка отправки teacher doc: %s", e)
                await bot.send_message(query.from_user.id, "Документ для учителя создан, но не удалось отправить его.")
        else:
            logger.error("Один или оба документа не были созданы: student=%s teacher=%s", student_path, teacher_path)
            await bot.send_message(query.from_user.id, "Документы не созданы из-за ошибки. Попробуйте позже.")

        await ProgressManager.safe_edit_progress(
            query.from_user.id, progress_msg.message_id, 100,
            "✅ Модификация завершена!", "🎉"
        )

    except Exception as e:
        logger.exception("Ошибка модификации вопросов: %s", e)
        try:
            await ProgressManager.safe_edit_progress(
                query.from_user.id, progress_msg.message_id, 0,
                "❗ Ошибка обработки.", "❌"
            )
        except Exception:
            logger.exception("Не удалось обновить прогресс при ошибке.")
        await bot.send_message(query.from_user.id, "Произошла ошибка. Попробуйте заново.")
    finally:
        try:
            await state.finish()
        except Exception:
            logger.exception("Не удалось завершить состояние FSM.")
        modify_sessions.pop(query.from_user.id, None)