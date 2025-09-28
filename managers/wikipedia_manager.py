import aiohttp
import wikipedia
from io import BytesIO
from typing import List, Optional, Dict
from utils.utils import get_aiohttp_session
import logging

logger = logging.getLogger("tg-edu-bot")

class WikipediaManager:
    @staticmethod
    async def search(query: str, lang: str = "ru", results: int = 20) -> List[str]:
        try:
            wikipedia.set_lang(lang)
            return wikipedia.search(query, results=results)
        except Exception as e:
            logger.error(f"Ошибка поиска в Википедии: {e}")
            return []

    @staticmethod
    async def get_page(title: str, lang: str = "ru") -> Optional[Dict]:
        try:
            wikipedia.set_lang(lang)
            page = wikipedia.page(title, auto_suggest=False)
            return {
                "title": page.title,
                "content": page.content,
                "summary": page.summary,
                "images": page.images,
                "url": page.url
            }
        except wikipedia.DisambiguationError as e:
            logger.warning(f"Неоднозначный запрос '{title}': {e}")
            return None
        except wikipedia.PageError as e:
            logger.warning(f"Страница не найдена '{title}': {e}")
            return None
        except Exception as e:
            logger.error(f"Ошибка получения страницы Википедии '{title}': {e}")
            return None

    @staticmethod
    async def download_image(url: str) -> Optional[BytesIO]:
        if not url.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
            return None

        session = get_aiohttp_session()
        try:
            async with session.get(url, timeout=30) as resp:
                if resp.status != 200:
                    return None

                content_type = resp.headers.get('Content-Type', '')
                if not any(img_type in content_type for img_type in ['image/jpeg', 'image/png', 'image/webp']):
                    return None

                image_data = await resp.read()
                buffer = BytesIO(image_data)
                buffer.seek(0)
                return buffer

        except Exception as e:
            logger.error(f"Ошибка скачивания изображения {url}: {e}")
            return None