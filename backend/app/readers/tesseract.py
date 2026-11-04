import io

from PIL import Image, ImageOps

from app.readers.base import ReaderResult, ReaderUnavailable
from app.readers.values import find_candidates

CONFIG = "--psm 6 -c tessedit_char_whitelist=0123456789."


class TesseractReader:
    """A free local fallback. It is weaker than the AI readers on LCD digits."""

    name = "TESSERACT"

    def available(self) -> bool:
        try:
            import pytesseract

            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def read(self, target: str, jpeg: bytes) -> ReaderResult:
        try:
            import pytesseract

            image = ImageOps.autocontrast(Image.open(io.BytesIO(jpeg)).convert("L"))
            if image.width < 1200:
                scale = 1200 / image.width
                image = image.resize((1200, max(1, int(image.height * scale))))
            candidates: list[str] = []
            for variant in (image, ImageOps.invert(image)):
                text = pytesseract.image_to_string(variant, config=CONFIG, timeout=15)
                for value in find_candidates(target, text):
                    if value not in candidates:
                        candidates.append(value)
        except Exception as exc:
            raise ReaderUnavailable("The local reader failed.") from exc

        # More than one candidate means the reader isn't sure, so it says nothing.
        if len(candidates) == 1:
            return ReaderResult(candidates[0])
        return ReaderResult(None)