import os
import logging
from datetime import datetime
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.types import InputFile

from core.bot import bot, dp
from states.states import States
from database.database_manager import DatabaseManager
from api.gemini_api import GeminiAPI
from api.image_generator import ImageGenerator
from api.document_generator import DocumentGenerator
from managers.keyboard_manager import KeyboardManager
from managers.progress_manager import ProgressManager
from utils.utils import user_exports, safe_state_transaction
from config.config import DATA_DIR

logger = logging.getLogger("tg-edu-bot")

def register_gen_handlers(dp: Dispatcher):
    dp.register_callback_query_handler(cb_start_gen, lambda c: c.data == "start_gen_cb")
    dp.register_message_handler(subject_handler, state=States.subject)
    dp.register_message_handler(topic_handler, state=States.topic)
    dp.register_message_handler(grade_handler, state=States.grade)
    dp.register_callback_query_handler(count_selected, lambda c: c.data and c.data.startswith("count:"), state=States.count)
    dp.register_callback_query_handler(lang_selected, lambda c: c.data.startswith("lang:"), state=States.language)
    dp.register_callback_query_handler(qtype_selected, lambda c: c.data.startswith("qtype:"), state=States.qtype)
    dp.register_callback_query_handler(confirm_gen, lambda c: c.data == "confirm_gen_cb", state="*")
    dp.register_callback_query_handler(cb_export_word, lambda c: c.data and c.data.startswith("export_word:"))

async def cb_start_gen(query: types.CallbackQuery):
    await query.answer()

    user = DatabaseManager.get_user(query.from_user.id)
    if not user or not user.get("accepted"):
        await bot.send_message(
            query.from_user.id,
            "🚫 Для генерации тестов требуется регистрация. Поделитесь номером телефона для активации всех функций.",
            reply_markup=KeyboardManager.get_main_kb(False)
        )
        return

    await bot.send_message(
        query.from_user.id,
        "Шаг 1 из 6: Укажите предмет (например, 'Математика', 'Биология'). Для отмены нажмите кнопку ниже.",
        reply_markup=KeyboardManager.get_cancel_kb()
    )
    await States.subject.set()

async def subject_handler(message: types.Message, state: FSMContext):
    text = GeminiAPI.sanitize_text(message.text)

    if text.lower() == "отмена":
        await state.finish()
        user_accepted = bool(DatabaseManager.get_user(message.from_user.id))
        await message.answer("Генерация отменена.", reply_markup=KeyboardManager.get_main_kb(user_accepted))
        return

    await state.update_data(subject=text)
    await message.answer(
        "Шаг 2 из 6: Укажите тему урока или теста (например, 'Квадратные уравнения').",
        reply_markup=KeyboardManager.get_cancel_kb()
    )
    await States.next()

async def topic_handler(message: types.Message, state: FSMContext):
    text = GeminiAPI.sanitize_text(message.text)

    if text.lower() == "отмена":
        await state.finish()
        user_accepted = bool(DatabaseManager.get_user(message.from_user.id))
        await message.answer("Генерация отменена.", reply_markup=KeyboardManager.get_main_kb(user_accepted))
        return

    await state.update_data(topic=text)
    await message.answer(
        "Шаг 3 из 6: Укажите класс или уровень (например, '7 класс', 'Начальный').",
        reply_markup=KeyboardManager.get_cancel_kb()
    )
    await States.next()

async def grade_handler(message: types.Message, state: FSMContext):
    text = GeminiAPI.sanitize_text(message.text)

    if text.lower() == "отмена":
        await state.finish()
        user_accepted = bool(DatabaseManager.get_user(message.from_user.id))
        await message.answer("Генерация отменена.", reply_markup=KeyboardManager.get_main_kb(user_accepted))
        return

    await state.update_data(grade=text)
    await message.answer(
        "Шаг 4 из 6: Выберите количество вопросов в тесте.",
        reply_markup=KeyboardManager.get_count_kb()
    )
    await States.next()

async def count_selected(query: types.CallbackQuery, state: FSMContext):
    await query.answer()

    try:
        count = int(query.data.split(":", 1)[1])
        if count not in (5, 10, 15):
            await query.answer("Недопустимое количество вопросов.", show_alert=True)
            return

        await state.update_data(count=count)
        await bot.send_message(
            query.from_user.id,
            "Шаг 5 из 6: Выберите язык для вопросов и ответов.",
            reply_markup=KeyboardManager.get_language_kb()
        )
        await States.next()

    except ValueError:
        await query.answer("Неверный выбор количества.", show_alert=True)

async def lang_selected(query: types.CallbackQuery, state: FSMContext):
    await query.answer()

    language = query.data.split(":", 1)[1]
    await state.update_data(language=language)

    await bot.send_message(
        query.from_user.id,
        "Шаг 6 из 6: Выберите тип вопросов — закрытые (с вариантами ответов) или открытые (требующие письменного ответа).",
        reply_markup=KeyboardManager.get_question_type_kb()
    )
    await States.next()

async def qtype_selected(query: types.CallbackQuery, state: FSMContext):
    await query.answer()

    qtype = query.data.split(":", 1)[1]
    await state.update_data(qtype=qtype)

    data = await state.get_data()
    summary = (
        "📋 <b>Проверьте параметры генерации теста:</b>\n\n"
        f"• Предмет: <b>{data.get('subject', 'Не указан')}</b>\n"
        f"• Тема: <b>{data.get('topic', 'Не указана')}</b>\n"
        f"• Класс: <b>{data.get('grade', 'Не указан')}</b>\n"
        f"• Количество вопросов: <b>{data.get('count', 5)}</b>\n"
        f"• Язык: <b>{data.get('language', 'Русский')}</b>\n"
        f"• Тип вопросов: <b>{'Открытые (краткий ответ)' if qtype == 'open' else 'Закрытые (варианты a-d)'}</b>\n\n"
        "Если всё верно, подтвердите. ИИ сгенерирует уникальные вопросы на основе ваших данных."
    )

    confirm_kb = KeyboardManager.inline([
        ("✅ Подтвердить и сгенерировать", "confirm_gen_cb"),
        ("❌ Отмена", "cancel_cb")
    ])

    await bot.send_message(query.from_user.id, summary, reply_markup=confirm_kb)

async def confirm_gen(query: types.CallbackQuery, state: FSMContext):
    await query.answer()

    try:
        data = await state.get_data()
        subject = data.get("subject", "")
        topic = data.get("topic", "")
        grade = data.get("grade", "")
        language = data.get("language", "Русский")
        count = int(data.get("count") or 5)
        qtype = data.get("qtype") or "closed"

        progress_msg = await bot.send_message(
            query.from_user.id,
            f"⏳ Подготовка к генерации... {ProgressManager.progress_bar(0)}"
        )

        await ProgressManager.safe_edit_progress(
            query.from_user.id, progress_msg.message_id, 10,
            "🛠 Формирую запрос для ИИ-модели...", "🚀"
        )

        tests, raw_response = await GeminiAPI.call_gemini(
            subject, topic, grade, language, count, qtype=qtype
        )

        if tests is None:
            await ProgressManager.safe_edit_progress(
                query.from_user.id, progress_msg.message_id, 0,
                "❗ Ошибка: не удалось получить данные от ИИ.", "❌"
            )

            error_snippet = raw_response if isinstance(raw_response, str) and len(raw_response) < 2000 else "Ответ слишком длинный или пустой"
            await bot.send_message(
                query.from_user.id,
                f"<b>Проблема с генерацией тестов.</b>\n\nДетали: {error_snippet}"
            )

            await state.finish()
            user_accepted = bool(DatabaseManager.get_user(query.from_user.id))
            await bot.send_message(
                query.from_user.id,
                "Попробуйте заново или измените параметры.",
                reply_markup=KeyboardManager.get_main_kb(user_accepted)
            )
            return

        await ProgressManager.safe_edit_progress(
            query.from_user.id, progress_msg.message_id, 40,
            "✅ Получены вопросы. Проверяю валидность...", "✅"
        )

        question_blocks = []
        answer_lines = []

        for idx, test in enumerate(tests, start=1):
            if qtype == "open":
                question_blocks.append(f"{idx}. {test['question']}")
                answer_lines.append(f"{idx}. {test.get('answer_text', '')}")
            else:
                question_blocks.append(f"{idx}. {test['question']}")
                options = test['options']
                question_blocks.append(f"   a) {options[0]}")
                question_blocks.append(f"   b) {options[1]}")
                question_blocks.append(f"   c) {options[2]}")
                question_blocks.append(f"   d) {options[3]}")
                question_blocks.append("")

                letters = ['a', 'b', 'c', 'd']
                answer_idx = test.get('answer', 1)
                answer_lines.append(f"{idx}. {letters[answer_idx-1]}")

        questions_text = "\n".join(question_blocks)
        answers_text = "🔑 <b>Правильные ответы:</b>\n" + "\n".join(answer_lines)

        meta = {
            "subject": subject,
            "topic": topic,
            "grade": grade,
            "language": language,
            "user_id": query.from_user.id,
            "qtype": qtype
        }

        json_path = DatabaseManager.save_test(query.from_user.id, meta, tests)

        await ProgressManager.safe_edit_progress(
            query.from_user.id, progress_msg.message_id, 60,
            "💾 Сохраняю данные в базу...", "💾"
        )

        header_buf = ImageGenerator.make_header_image(
            f"{subject} • {topic}",
            f"Класс: {grade}",
            username=(query.from_user.username or str(query.from_user.id))
        )

        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(json_path)[0]

        student_docx = base_name + "_student.docx"
        teacher_docx = base_name + "_teacher.docx"

        student_path = DocumentGenerator.create_docx_file(
            meta, tests, header_buf, student_docx, False, qtype
        )
        teacher_path = DocumentGenerator.create_docx_file(
            meta, tests, header_buf, teacher_docx, True, qtype
        )

        if student_path and teacher_path:
            user_exports[query.from_user.id] = {
                "json_path": json_path,
                "student_docx": student_path,
                "teacher_docx": teacher_path,
                "created_at": datetime.utcnow().isoformat()
            }
        else:
            user_exports.pop(query.from_user.id, None)
            await bot.send_message(
                query.from_user.id,
                "❗ Не удалось создать документы Word. Проверьте настройки."
            )

        await ProgressManager.safe_edit_progress(
            query.from_user.id, progress_msg.message_id, 80,
            "📤 Формирую текст для отправки...", "📤"
        )

        if len(questions_text) <= 4000:
            await bot.send_message(
                query.from_user.id,
                "<b>Сгенерированные вопросы:</b>\n\n" + questions_text,
                parse_mode="HTML"
            )
        else:
            txt_filename = os.path.join(DATA_DIR, f"questions_{query.from_user.id}_{ts}.txt")
            with open(txt_filename, "w", encoding="utf-8") as f:
                f.write(questions_text)

            with open(txt_filename, "rb") as f:
                await bot.send_document(
                    query.from_user.id,
                    InputFile(f, filename=f"Вопросы_{ts}.txt"),
                    caption="Сгенерированные вопросы (текстовый файл)"
                )
            os.remove(txt_filename)

        await bot.send_message(query.from_user.id, answers_text, parse_mode="HTML")

        if user_exports.get(query.from_user.id):
            export_kb = types.InlineKeyboardMarkup(row_width=1)
            export_kb.add(types.InlineKeyboardButton(
                "📄 Скачать Word для учеников (без ответов)",
                callback_data=f"export_word:{query.from_user.id}:student"
            ))
            export_kb.add(types.InlineKeyboardButton(
                "📝 Скачать Word для учителя (с ответами)",
                callback_data=f"export_word:{query.from_user.id}:teacher"
            ))

            await bot.send_message(
                query.from_user.id,
                "Документы в формате Microsoft Word готовы. Скачайте их ниже для печати или редактирования.",
                reply_markup=export_kb
            )

        await ProgressManager.safe_edit_progress(
            query.from_user.id, progress_msg.message_id, 100,
            "✅ Генерация завершена успешно!", "🎉"
        )

        user_accepted = bool(DatabaseManager.get_user(query.from_user.id))
        await bot.send_message(
            query.from_user.id,
            "Если нужно создать ещё тесты, нажмите соответствующую кнопку в меню. Удачи на уроках! 📖",
            reply_markup=KeyboardManager.get_main_kb(user_accepted)
        )

    except Exception as e:
        logger.error(f"Ошибка в генерации теста: {e}")
        await ProgressManager.safe_edit_progress(
            query.from_user.id, progress_msg.message_id, 0,
            "❗ Произошла ошибка во время генерации.", "❌"
        )
        await bot.send_message(
            query.from_user.id,
            "Извините, произошла техническая ошибка. Попробуйте позже или свяжитесь с администратором."
        )
    finally:
        await state.finish()

async def cb_export_word(query: types.CallbackQuery):
    await query.answer()

    try:
        parts = query.data.split(":")
        user_id = int(parts[1])
        mode = parts[2] if len(parts) > 2 else "student"

        if query.from_user.id != user_id:
            await query.answer("Этот файл доступен только вам.", show_alert=True)
            return

        export_info = user_exports.get(user_id)
        if not export_info:
            await query.answer("Файл не найден или срок действия истек.", show_alert=True)
            return

        file_key = "teacher_docx" if mode == "teacher" else "student_docx"
        file_path = export_info.get(file_key)

        if not file_path or not os.path.exists(file_path):
            await query.answer("Файл не найден.", show_alert=True)
            return

        with open(file_path, "rb") as f:
            caption = ("Документ Word для учителя (с ответами)" if mode == "teacher"
                       else "Документ Word для учеников (без ответов)")

            await bot.send_document(
                query.from_user.id,
                InputFile(f, filename=os.path.basename(file_path)),
                caption=caption
            )

    except Exception as e:
        logger.error(f"Ошибка экспорта Word: {e}")
        await query.answer("Ошибка при отправке файла. Попробуйте позже.", show_alert=True)