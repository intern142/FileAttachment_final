import os
import uuid
import pytesseract
from PIL import Image
from pdf2image import convert_from_bytes
from typing import Tuple


def extract_text(file_bytes: bytes, filename: str) -> Tuple[str, str]:
    """
    Extract text from image or PDF file.
    Returns (job_id, extracted_text)
    """
    job_id = str(uuid.uuid4())
    ext = os.path.splitext(filename.lower())[1]
    
    if ext == ".pdf":
        text = _extract_from_pdf(file_bytes)
    else:
        text = _extract_from_image(file_bytes)
    
    return job_id, text


def _extract_from_image(file_bytes: bytes) -> str:
    import io
    image = Image.open(io.BytesIO(file_bytes))
    text = pytesseract.image_to_string(image)
    return text


def _extract_from_pdf(file_bytes: bytes) -> str:
    images = convert_from_bytes(file_bytes)
    texts = []
    for image in images:
        text = pytesseract.image_to_string(image)
        texts.append(text)
    return "\n\n".join(texts)


def parse_ocr_text(text: str) -> dict:
    """
    Basic parsing of OCR text to extract structured fields.
    Returns dict with contractor, source, date, amount.
    """
    result = {
        "contractor": None,
        "source": None,
        "date": None,
        "amount": None
    }
    
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    for line in lines:
        lower = line.lower()
        
        if any(kw in lower for kw in ["contractor", "vendor", "supplier", "from:"]):
            result["contractor"] = _clean_value(line)
        elif any(kw in lower for kw in ["source", "category", "type:"]):
            result["source"] = _clean_value(line)
        elif any(kw in lower for kw in ["date", "invoice date", "bill date"]):
            result["date"] = _clean_value(line)
        elif any(kw in lower for kw in ["amount", "total", "sum", "₹", "$", "rs"]):
            result["amount"] = _clean_value(line)
    
    return result


def _clean_value(line: str) -> str:
    import re
    value = re.sub(r'^(contractor|vendor|supplier|from|source|category|type|date|invoice date|bill date|amount|total|sum)[:\s]*', '', line, flags=re.IGNORECASE)
    return value.strip()