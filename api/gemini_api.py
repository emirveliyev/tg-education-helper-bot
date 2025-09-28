# api/gemini_api.py
import re
import json
import aiohttp
import asyncio
from typing import Optional, List, Tuple, Dict

from config.config import API_BASE, GEMINI_MODEL, GEMINI_API_KEY, MAX_OUTPUT_TOKENS, TEMPERATURE
from utils.utils import GEMINI_SEMAPHORE, get_aiohttp_session
import logging

logger = logging.getLogger("tg-edu-bot")

class GeminiAPI:
    @staticmethod
    def sanitize_text(text: str) -> str:
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def extract_json_array(text: str) -> Optional[List]:
        if not text:
            return None

        text = re.sub(r"```(?:json)?", "", text).strip()

        try:
            obj = json.loads(text)
            if isinstance(obj, list):
                return obj
        except json.JSONDecodeError:
            pass

        matches = re.findall(r'($$   \s*\{.*?\}\s*   $$)', text, re.DOTALL)
        for match in matches:
            try:
                obj = json.loads(match)
                if isinstance(obj, list):
                    return obj
            except json.JSONDecodeError:
                continue

        return None

    @staticmethod
    async def call_api(session: aiohttp.ClientSession, url: str, headers: Dict, payload: Dict, timeout: int = 120) -> Tuple[Optional[Dict], Optional[str]]:
        try:
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return None, f"HTTP ошибка {resp.status}: {text[:400]}"

                data = await resp.json()
                return data, None

        except asyncio.TimeoutError:
            return None, "Таймаут запроса к API"
        except Exception as e:
            return None, f"Неизвестная ошибка: {str(e)}"

    @staticmethod
    async def call_gemini(subject: str, topic: str, grade: str, language: str, n_questions: int,
                          qtype: str = "closed", context_examples: Optional[List] = None,
                          modify_mode: Optional[str] = None) -> Tuple[Optional[List], Optional[str]]:
        if not API_BASE or not GEMINI_MODEL or not GEMINI_API_KEY:
            return None, "Настройки API для ИИ не заданы"

        if qtype == "open":
            prompt = (
                "Ты — опытный педагог и автор образовательных тестов. Создай ровно {N} открытых вопросов, "
                "требующих краткого ответа (1-3 предложения). Каждый вопрос должен быть уникальным по "
                "формулировке и уровню сложности. Предмет: {SUBJECT}. Тема: {TOPIC}. Класс: {GRADE}. "
                "Язык: {LANG}. Верни строго JSON-массив длины {N}. Каждый элемент: "
                "{{\"question\": \"строка\", \"answer\": \"строка\"}}. "
                "Без дополнительных комментариев, объяснений или блоков кода — только чистый JSON."
            ).format(
                N=n_questions,
                SUBJECT=subject or "Предмет",
                TOPIC=topic or "Тема",
                GRADE=grade or "",
                LANG=language or "Русский"
            )
        else:
            prompt = (
                "Ты — опытный педагог и автор образовательных тестов. Создай ровно {N} закрытых вопросов "
                "с четырьмя вариантами ответа. Каждый вопрос должен быть уникальным по формулировке и "
                "уровню сложности. Предмет: {SUBJECT}. Тема: {TOPIC}. Класс: {GRADE}. Язык: {LANG}. "
                "Верни строго JSON-массив длины {N}. Каждый элемент: "
                "{{\"question\": \"строка\", \"options\": [\"вариант1\", \"вариант2\", \"вариант3\", \"вариант4\"], "
                "\"answer\": число от 1 до 4}}. Без дополнительных комментариев, объяснений или блоков кода — "
                "только чистый JSON."
            ).format(
                N=n_questions,
                SUBJECT=subject or "Предмет",
                TOPIC=topic or "Тема",
                GRADE=grade or "",
                LANG=language or "Русский"
            )

        if context_examples:
            try:
                ctx = json.dumps(context_examples, ensure_ascii=False, indent=2)
                prompt += f"\n\nИспользуй эти примеры для вдохновения:\n{ctx}"
            except Exception as e:
                logger.error(f"Ошибка при добавлении контекста: {e}")

        if modify_mode:
            if modify_mode == "change_topic":
                prompt = ("Сохрани математические формулы и логику решения для каждого вопроса, но измени "
                          "тему, контекст и формулировки, чтобы ответы остались аналогичными. ") + prompt
            elif modify_mode == "change_variables":
                prompt = ("Сохрани тему, структуру и логику решения, но измени числовые значения, "
                          "переменные и детали, чтобы ответы изменились соответственно. ") + prompt

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": TEMPERATURE,
                "maxOutputTokens": MAX_OUTPUT_TOKENS
            }
        }

        session = get_aiohttp_session()
        url = f"{API_BASE}/models/{GEMINI_MODEL}:generateContent"
        headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}

        last_error = None

        async with GEMINI_SEMAPHORE:
            for attempt in range(1, 4):
                data, error = await GeminiAPI.call_api(session, url, headers, payload)

                if error:
                    last_error = error
                    wait_time = 1.5 * attempt
                    logger.warning(f"Попытка {attempt} не удалась: {error}. Жду {wait_time} сек.")
                    await asyncio.sleep(wait_time)
                    continue

                try:
                    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError, TypeError):
                    last_error = "Неверный формат ответа от API"
                    continue

                parsed = GeminiAPI.extract_json_array(raw_text)
                if parsed is None:
                    last_error = f"Не удалось извлечь JSON: {raw_text[:400]}"
                    continue

                validated = []
                validation_error = False

                if qtype == "open":
                    for i, item in enumerate(parsed):
                        try:
                            question = GeminiAPI.sanitize_text(item["question"])
                            answer = GeminiAPI.sanitize_text(item.get("answer", ""))

                            if not question or not answer:
                                logger.warning(f"Пустые поля в вопросе {i+1}")
                                validation_error = True
                                break

                            validated.append({
                                "question": question,
                                "answer_text": answer,
                                "index": i + 1
                            })

                        except KeyError as e:
                            logger.warning(f"Отсутствует ключ в вопросе {i+1}: {e}")
                            validation_error = True
                            break
                        except Exception as e:
                            logger.error(f"Ошибка валидации открытого вопроса {i+1}: {e}")
                            validation_error = True
                            break
                else:
                    for i, item in enumerate(parsed):
                        try:
                            question = GeminiAPI.sanitize_text(item["question"])
                            options = [GeminiAPI.sanitize_text(x) for x in item["options"]]
                            answer = int(item["answer"])

                            if len(options) != 4:
                                logger.warning(f"Неверное количество вариантов в вопросе {i+1}: {len(options)}")
                                validation_error = True
                                break

                            if answer < 1 or answer > 4:
                                logger.warning(f"Неверный индекс ответа в вопросе {i+1}: {answer}")
                                validation_error = True
                                break

                            if any(not opt for opt in options):
                                logger.warning(f"Пустые варианты ответа в вопросе {i+1}")
                                validation_error = True
                                break

                            validated.append({
                                "question": question,
                                "options": options,
                                "answer": answer,
                                "index": i + 1
                            })

                        except (KeyError, ValueError, TypeError) as e:
                            logger.warning(f"Ошибка валидации закрытого вопроса {i+1}: {e}")
                            validation_error = True
                            break
                        except Exception as e:
                            logger.error(f"Неизвестная ошибка валидации вопроса {i+1}: {e}")
                            validation_error = True
                            break

                if validation_error or len(validated) != n_questions:
                    last_error = f"Неверное количество или структура вопросов: ожидалось {n_questions}, получено {len(validated)}"
                    continue

                return validated, raw_text

        return None, last_error

    @staticmethod
    async def call_gemini_for_text_improvement(text: str, language: str = "Русский") -> str:
        prompt = (
            "Ты — редактор образовательного контента. Улучши этот текст: сделай его более связным, "
            "добавь структуру (заголовки, абзацы), удали повторы, сделай язык ясным и увлекательным. "
            "Сохрани все ключевые факты. Язык: {LANG}. Верни улучшенный текст без дополнительных комментариев."
        ).format(LANG=language)

        payload = {
            "contents": [{"parts": [{"text": prompt + "\n\nОригинальный текст:\n" + text}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": MAX_OUTPUT_TOKENS}
        }

        session = get_aiohttp_session()
        url = f"{API_BASE}/models/{GEMINI_MODEL}:generateContent"
        headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}

        async with GEMINI_SEMAPHORE:
            try:
                async with session.post(url, headers=headers, json=payload, timeout=120) as resp:
                    if resp.status != 200:
                        logger.warning(f"Ошибка API при улучшении текста: {resp.status}")
                        return text

                    data = await resp.json()
                    improved_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    return improved_text

            except Exception as e:
                logger.error(f"Ошибка улучшения текста: {e}")
                return text