"""Check and normalise an uploaded photo before anything reads it."""
import io

from PIL import Image, ImageOps

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 25_000_000
MAX_SIDE = 1600
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


def prepare_image(data: bytes) -> bytes:
    """Validate a photo and return a clean, smaller JPEG without metadata.

    Raises ValueError with a message that is safe to show to the clerk.
    """
    if not data:
        raise ValueError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise ValueError("The photo is larger than 5 MB.")

    try:
        probe = Image.open(io.BytesIO(data))
        if probe.format not in ALLOWED_FORMATS:
            raise ValueError("Use a JPEG, PNG or WebP photo.")
        width, height = probe.size
        if width * height > MAX_PIXELS:
            raise ValueError("The photo is too large. Use a smaller photo.")
        probe.verify()
        image = Image.open(io.BytesIO(data))
        image.load()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("That file isn't a readable photo.") from exc

    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=85)
    return out.getvalue()