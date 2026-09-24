import io
import os
import re
from typing import Optional

try:
    import pytesseract
    from pdf2image import convert_from_bytes
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

if OCR_AVAILABLE:
    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        candidates = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Tesseract-OCR", "tesseract.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Tesseract-OCR", "tesseract.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Tesseract-OCR", "tesseract.exe"),
        ]
        for path in candidates:
            if os.path.isfile(path):
                pytesseract.pytesseract.tesseract_cmd = path
                break


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")
SUPPORTED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".pdf", ".bmp", ".tif", ".tiff")
UNKNOWN_VALUE = "UNKNOWN"

# Labels that identify the contracting party (who issued / is billing).
CONTRACTOR_LABELS = (
    "contractor",
    "contractor name",
    "name of contractor",
    "contracted by",
    "billed by",
    "bill from",
    "invoice from",
    "issued by",
    "prepared by",
)

# Labels that identify the place(s) goods were purchased from.
PURCHASED_FROM_LABELS = (
    "purchased from",
    "purchased at",
    "purchase from",
    "bought from",
    "purchase location",
    "sold by",
    "store",
    "merchant",
    "supplier",
    "shop",
    "vendor",
)

_KNOWN_LABELS = CONTRACTOR_LABELS + PURCHASED_FROM_LABELS

# Markers that signal the end of an extracted value on a noisy OCR line
# (e.g. "Contractor: ACME Ltd PO Number:P0-UK-78421" -> "ACME Ltd").
_BOUNDARY_RE = re.compile(
    r"(?:^|\s+)(?:"
    r"P\.?\s?O\.?\s*(?:number|no|#|order)"
    r"|purchase\s+order"
    r"|invoice\s*(?:number|no|#)"
    r"|invoice\s*:"
    r"|reference\s*:"
    r"|ref\s*:"
    r"|client\s*:"
    r"|property\s*:"
    r"|invoice\s+date"
    r"|service\s+date"
    r"|contractor\s+ref"
    r"|payment\s+terms"
    r"|account\s*(?:number|no|#)"
    r"|vat\s*(?:number|no|#|:)"
    r"|tax\s*id"
    r"|(?:tel|phone|telephone)\s*:"
    r"|email\s*:"
    r"|www\."
    r"|https?://"
    r")",
    re.IGNORECASE,
)

# Lines starting with these keywords are treated as document boilerplate,
# never as a company heading.
_HEADING_SKIP = (
    "invoice", "receipt", "tax invoice", "contractor invoice",
    "page ", "job ", "work order", "estimate", "quotation", "quote",
    "bill to", "payment", "date:", "total", "amount", "description",
    "delivery", "order no", "credit note", "statement", "source:",
    "client:", "subtotal", "balance",
)


def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """Run OCR on an uploaded invoice image/PDF. Reuses the original OCR pipeline."""
    if not OCR_AVAILABLE:
        return "OCR not available - pytesseract/pdf2image not installed"
    ext = os.path.splitext(filename or "")[1].lower()
    try:
        if ext in IMAGE_EXTENSIONS:
            image = Image.open(io.BytesIO(file_bytes))
            return pytesseract.image_to_string(image)
        if ext == ".pdf":
            images = convert_from_bytes(file_bytes)
            text = ""
            for img in images:
                text += pytesseract.image_to_string(img) + "\n"
            return text
        return f"Unsupported file type: {ext}"
    except Exception as e:
        return f"OCR error: {str(e)}"


def has_ocr_error(ocr_text: str) -> bool:
    return (
        not ocr_text
        or ocr_text.startswith("OCR not available")
        or ocr_text.startswith("OCR error")
        or ocr_text.startswith("Unsupported file type")
    )


def _clean_value(value: str) -> str:
    value = value.replace("\r", " ").replace("\n", " ")
    value = re.sub(r"\s+", " ", value).strip()
    value = value.strip("|Â·â€¢")
    value = value.strip(" -â€“â€”")
    value = value.strip(":;,. ")
    return value.strip()


def _truncate_at_boundary(value: str) -> str:
    match = _BOUNDARY_RE.search(value)
    if match:
        return value[:match.start()]
    return value


def _extract_labeled(text: str, labels) -> Optional[str]:
    """Find 'Label: value' patterns. Longer labels are matched first."""
    for label in sorted(labels, key=len, reverse=True):
        pattern = re.compile(
            rf"(?<![A-Za-z]){re.escape(label)}\s*:\s*(?P<value>[^\n]+)",
            re.IGNORECASE,
        )
        match = pattern.search(text)
        if not match:
            continue
        value = _clean_value(_truncate_at_boundary(match.group("value")))
        if value:
            return value
    return None


def _is_labeled_line(line: str) -> bool:
    low = line.lower().lstrip()
    for label in _KNOWN_LABELS:
        if re.match(rf"(?<![A-Za-z]){re.escape(label)}\s*:", low):
            return True
    return False


def _extract_heading(text: str) -> Optional[str]:
    """Fallback: the first non-boilerplate line is usually the company (header)."""
    for raw in text.splitlines():
        line = raw.strip()
        if len(line) < 3:
            continue
        low = line.lower()
        if any(low.startswith(s) for s in _HEADING_SKIP):
            continue
        if _is_labeled_line(line):
            continue
        value = _clean_value(_truncate_at_boundary(line))
        if not value:
            continue
        if not re.search(r"[A-Za-z]", value):
            continue
        if re.fullmatch(r"[\d\s\W]+", value):
            continue
        return value
    return None


def extract_invoice_fields(ocr_text: str) -> dict:
    """Extract Contractor and Purchased From from OCR text."""
    contractor = _extract_labeled(ocr_text, CONTRACTOR_LABELS)
    if contractor is None:
        contractor = _extract_heading(ocr_text)
    purchased_from = _extract_labeled(ocr_text, PURCHASED_FROM_LABELS)
    return {
        "contractor": contractor or UNKNOWN_VALUE,
        "purchased_from": purchased_from or UNKNOWN_VALUE,
    }
