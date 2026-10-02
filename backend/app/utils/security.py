import os
import re
from pathlib import Path


def sanitize_ocr_text(text: str) -> str:
    """Remove HTML tags and potential XSS payloads from OCR text."""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
    text = re.sub(r'on\w+\s*=', '', text, flags=re.IGNORECASE)
    return text.strip()


def get_relative_file_path(file_path: str, storage_path: str) -> str:
    """Convert absolute file path to relative path for API responses."""
    try:
        storage = Path(storage_path).resolve()
        file = Path(file_path).resolve()
        if str(file).startswith(str(storage)):
            return str(file.relative_to(storage))
    except Exception:
        pass
    return os.path.basename(file_path)