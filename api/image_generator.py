# api/image_generator.py
from io import BytesIO
from datetime import datetime
from typing import Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
from api.gemini_api import GeminiAPI
import logging

logger = logging.getLogger("tg-edu-bot")

class ImageGenerator:
    @staticmethod
    def make_header_image(title: str, subtitle: str = "", username: str = "", size: Tuple[int, int] = (1600, 420)) -> Optional[BytesIO]:
        try:
            img = Image.new("RGB", size, (18, 32, 63))
            draw = ImageDraw.Draw(img)

            try:
                font_title = ImageFont.truetype("arialbd.ttf", 56)
                font_sub = ImageFont.truetype("arial.ttf", 28)
                font_meta = ImageFont.truetype("arial.ttf", 18)
            except IOError:
                font_title = ImageFont.load_default()
                font_sub = ImageFont.load_default()
                font_meta = ImageFont.load_default()

            title_clean = GeminiAPI.sanitize_text(title)
            subtitle_clean = GeminiAPI.sanitize_text(subtitle)

            padding = 40
            x = padding
            y = padding

            draw.text((x + 2, y + 2), title_clean, font=font_title, fill=(0, 0, 0, 140))
            draw.text((x, y), title_clean, font=font_title, fill=(255, 255, 255, 255))

            if subtitle_clean:
                draw.text((x, y + 80), subtitle_clean, font=font_sub, fill=(230, 230, 240, 220))

            meta_text = f"Создано: {datetime.utcnow().strftime('%Y-%m-%d')} • Пользователь: {username}"
            text_width = len(meta_text) * 10
            meta_x = size[0] - padding - text_width
            meta_y = size[1] - padding - 20
            draw.text((meta_x, meta_y), meta_text, font=font_meta, fill=(200, 200, 200, 200))

            buf = BytesIO()
            img.save(buf, format="PNG", optimize=True)
            buf.seek(0)
            return buf

        except Exception as e:
            logger.error(f"Ошибка создания заголовочного изображения: {e}")
            return None