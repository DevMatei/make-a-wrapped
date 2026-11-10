"""Re-encode untrusted API artwork in a resource-limited worker process."""

from __future__ import annotations

import io
import sys
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_INPUT_BYTES = 10 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
MAX_EDGE = 2048


def sanitize(data: bytes) -> bytes:
    if not data or len(data) > MAX_INPUT_BYTES:
        raise ValueError("Artwork exceeds its upload size limit.")

    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    try:
        with Image.open(io.BytesIO(data), formats=("PNG", "JPEG", "WEBP")) as image:
            image.verify()
        with Image.open(io.BytesIO(data), formats=("PNG", "JPEG", "WEBP")) as image:
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("Animated artwork is not supported.")
            width, height = image.size
            if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
                raise ValueError("Artwork exceeds its pixel limit.")
            image.load()
            image = ImageOps.exif_transpose(image)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "transparency" in image.info else "RGB")
            image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.BICUBIC, reducing_gap=2.0)
            output = io.BytesIO()
            image.save(output, format="WEBP", quality=88, method=2)
            result = output.getvalue()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, UnidentifiedImageError, OSError) as exc:
        raise ValueError("Artwork must be a valid PNG, JPEG, or WebP image within the pixel limit.") from exc

    if not result or len(result) > MAX_OUTPUT_BYTES:
        raise ValueError("Sanitized artwork exceeds its output size limit.")
    return result


def main() -> int:
    data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    try:
        sys.stdout.buffer.write(sanitize(data))
        return 0
    except (ValueError, OSError) as exc:
        sys.stderr.write(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
