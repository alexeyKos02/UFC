"""Проверка и сохранение изображений.

Тип определяется по содержимому файла, а затем картинка пересохраняется:
так отбрасываются метаданные и всё, что было приклеено к файлу после изображения.
"""

import io
import uuid
import warnings

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings
from app.errors import AppError

FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_DIMENSION = 2000
MAX_PIXELS = 40_000_000


def _reject_type() -> AppError:
    return AppError(415, "Загрузите изображение в формате JPEG, PNG или WEBP")


def _decode(data: bytes) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            probe = Image.open(io.BytesIO(data))
            if probe.format not in FORMATS:
                raise _reject_type()
            if probe.width * probe.height > MAX_PIXELS:
                raise AppError(413, "Изображение слишком большое по разрешению")
            probe.verify()
            image = Image.open(io.BytesIO(data))
            image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        raise _reject_type() from None
    return image


def save_image(upload: UploadFile, folder: str) -> str:
    if upload.content_type not in ALLOWED_CONTENT_TYPES:
        raise _reject_type()
    data = upload.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes // (1024 * 1024)
        raise AppError(413, f"Файл слишком большой, максимум {limit_mb} МБ")

    image = _decode(data)
    image_format = image.format
    image = ImageOps.exif_transpose(image)
    image.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
    if image_format == "JPEG" and image.mode != "RGB":
        image = image.convert("RGB")

    relative_path = f"{folder}/{uuid.uuid4().hex}{FORMATS[image_format]}"
    target = settings.upload_dir / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, format=image_format)
    return relative_path


# Фон считается прозрачным, если по верхнему, левому и правому краю картинки прозрачна
# большая часть точек: вырезанная фигура края не касается (кроме ног снизу).
CUTOUT_ALPHA = 32
CUTOUT_EDGE_SHARE = 0.6


def is_cutout(image: Image.Image) -> bool:
    if "A" not in image.getbands() and "transparency" not in image.info:
        return False
    alpha = image.convert("RGBA").getchannel("A")
    width, height = alpha.size
    step_x = max(1, width // 200)
    step_y = max(1, height // 200)
    edge = [alpha.getpixel((x, 0)) for x in range(0, width, step_x)]
    edge += [alpha.getpixel((0, y)) for y in range(0, height, step_y)]
    edge += [alpha.getpixel((width - 1, y)) for y in range(0, height, step_y)]
    return sum(1 for value in edge if value < CUTOUT_ALPHA) >= CUTOUT_EDGE_SHARE * len(edge)


def stored_is_cutout(relative_path: str | None) -> bool:
    """Проверка уже сохранённого файла; нет файла или он не читается — не вырезанная фигура."""
    if not relative_path:
        return False
    try:
        with Image.open(settings.upload_dir / relative_path) as image:
            return is_cutout(image)
    except (OSError, ValueError):
        return False


def delete_image(relative_path: str | None) -> None:
    if relative_path:
        (settings.upload_dir / relative_path).unlink(missing_ok=True)
