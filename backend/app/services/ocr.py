import os
import uuid
import re
import pytesseract
from PIL import Image
from pdf2image import convert_from_bytes
from typing import Tuple


def _sanitize_text(text: str) -> str:
    """Remove HTML tags and potential XSS payloads from text."""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
    text = re.sub(r'on\w+\s*=', '', text, flags=re.IGNORECASE)
    return text.strip()


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
    
    return job_id, _sanitize_text(text)


def _extract_from_image(file_bytes: bytes) -> str:
    import io
    image = Image.open(io.BytesIO(file_bytes))
    text = pytesseract.image_to_string(image)
    return _sanitize_text(text)


def _extract_from_pdf(file_bytes: bytes) -> str:
    images = convert_from_bytes(file_bytes)
    texts = []
    for image in images:
        text = pytesseract.image_to_string(image)
        texts.append(text)
    return _sanitize_text("\n\n".join(texts))


def parse_ocr_text(text: str) -> dict:
    """
    Parse OCR text to extract structured fields.
    Handles multiple invoice formats including:
    - "Contractor: X" / "Source: Y" format
    - "From: X" / "To: Y" format
    - Company names in first few lines
    - Date patterns
    - Amount patterns
    """
    result = {
        "contractor": None,
        "source": None,
        "date": None,
        "amount": None
    }
    
    lines = [line.strip() for line in text.split('\n') if line.strip()]

    # First pass: look for explicit labels. First confident match wins;
    # later incidental mentions (e.g. "contractor account" in payment terms)
    # must not overwrite a good value.
    for line in lines:
        lower = line.lower()

        if not result["contractor"] and any(kw in lower for kw in ["contractor", "vendor", "supplier", "from:", "billed by", "sold by", "company:"]):
            value = _parse_labeled_value(line)
            if _is_plausible_name(value):
                result["contractor"] = value

        if not result["source"] and any(kw in lower for kw in ["source", "purchase", "purchased from", "item:", "description:", "supplier:", "vendor:"]):
            value = _parse_labeled_value(line)
            if _is_plausible_name(value):
                result["source"] = value

        if not result["date"]:
            result["date"] = _extract_date_from_line(line)

        if not result["amount"] and re.search(r'\b(amount|total|price|cost|value|balance)\b|:\s*\s*[£$€₹]', lower):
            candidate = _extract_amount_from_line(line)
            if candidate:
                result["amount"] = candidate

    # Second pass: if no explicit labels found, try heuristics
    if not result["contractor"]:
        result["contractor"] = _guess_company_name(lines)

    if not result["source"]:
        result["source"] = _guess_source(lines)

    if not result["date"]:
        result["date"] = _guess_date(text)

    if not result["amount"]:
        result["amount"] = _guess_amount(text)

    return result


_LABEL_BOUNDARY = re.compile(
    r'\s+(?:po number|po#|p\.o\.|client|source|property|service|invoice|date|ref|ref\.|reference|payment|bank|page|vat|total|amount|description|location|qty|net|gross|bill|ship)\b',
    re.IGNORECASE,
)

_BAD_VALUE_WORDS = re.compile(
    r'payment|terms|bank|invoice|receipt|page|notes|ocr|http|www|email|tel|phone|due|subtotal|total',
    re.IGNORECASE,
)


def _parse_labeled_value(line: str) -> str:
    """Extract the value of a labeled line, cutting off trailing inline labels."""
    if ':' in line:
        value = line.split(':', 1)[1].strip()
    else:
        # Handle OCR'd labels missing a colon, e.g. "Contractor ABC Ltd"
        m = re.match(r'^\s*(contractor|vendor|supplier|source|purchased from|from|billed by|sold by|company)\s*[:\-–]?\s+(.+)$', line, re.IGNORECASE)
        if not m:
            return None
        value = m.group(2).strip()
    value = _LABEL_BOUNDARY.split(value, maxsplit=1)[0].strip()
    value = value.strip(' -–|:')
    return value or None


def _is_plausible_name(value) -> bool:
    if not value:
        return False
    if len(value) > 80 or len(value) < 2:
        return False
    if '|' in value:
        return False
    if re.search(r'[£$€₹]|\d+[.,]\d{2}|%|\b(?:20\d{2})\b', value):
        return False
    if _BAD_VALUE_WORDS.search(value):
        return False
    # Reject values that are just a re-stated label/reference
    if re.fullmatch(r'(contractor|vendor|supplier|source|client|ref|reference|unknown|n/?a)', value, re.IGNORECASE):
        return False
    if re.match(r'(?i)^(ref|ref\.|contractor ref|invoice|po|p\.o\.)', value):
        return False
    return True


def _extract_date_from_line(line: str):
    lower = line.lower()
    has_date_word = 'date' in lower or 'dated' in lower or 'issued' in lower
    if not has_date_word or 'due' in lower:
        return None
    for pattern in _DATE_PATTERNS:
        m = re.search(pattern, line)
        if m:
            return _normalize_date(m.group(1), line)
    return None


_DATE_PATTERNS = [
    r'(?<![0-9])(\d{4}[-/]\d{2}[-/]\d{2})(?![0-9])',
    r'(?<![0-9])(\d{1,2}[-/]\d{1,2}[-/]\d{4})(?![0-9])',
    r'(?<![A-Za-z0-9])(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})(?![0-9])',
    r'(?<![A-Za-z0-9])((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})(?![0-9])',
]


def _normalize_date(date_str: str, context: str = '') -> str:
    try:
        if re.match(r'\d{4}[-/]\d{2}[-/]\d{2}', date_str):
            return date_str.replace('/', '-')
        parts = date_str.replace('/', '-').split('-')
        if len(parts) == 3:
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
            # Prefer day-first when the invoice looks UK-formatted
            uk_hint = bool(re.search(r'£|GBP|vat', context, re.IGNORECASE))
            if day > 12:
                return f"{year}-{month:02d}-{day:02d}"
            if uk_hint:
                return f"{year}-{month:02d}-{day:02d}"
            # Unknown ordering; default to day-first as invoices are commonly DD/MM/YYYY
            return f"{year}-{month:02d}-{day:02d}"
        return date_str
    except Exception:
        return date_str


def _extract_amount_from_line(line: str):
    m = re.search(r'[£$€₹]\s*(\d+(?:,\d{3})*(?:\.\d{2})?)|(\d+(?:,\d{3})*(?:\.\d{2}))\s*(?:USD|EUR|GBP|INR)', line)
    if m:
        return (m.group(1) or m.group(2)).replace(',', '')
    m = re.search(r'(?:total|amount|price|cost|value)[:\s]*[£$€₹]?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)', line, re.IGNORECASE)
    if m:
        return m.group(1).replace(',', '')
    return None


def _guess_company_name(lines: list) -> str:
    """Guess company name from first non-empty lines that look like a company name."""
    import re
    for line in lines[:10]:  # Check first 10 lines
        # Skip common non-company lines
        lower = line.lower()
        if any(skip in lower for skip in ['invoice', 'bill', 'receipt', 'date', 'total', 'amount', 'tax', 'vat', 'gst', 'no.', 'number', 'page', 'tel', 'phone', 'fax', 'email', 'www', 'http', 'payment', 'terms', 'bank', 'client', 'address', 'po ']):
            continue
        if ':' in line:
            continue
        if not _is_plausible_name(line):
            continue

        # Look for patterns like "ABC Corp", "XYZ Ltd", "Company Name Inc"
        if re.match(r'^[A-Z][a-zA-Z\s&\.,\-]+(?:Corp|Corporation|Inc|Ltd|LLC|Company|Co\.|Group|Enterprises|Industries|Services|Solutions|Systems|Technologies|Tech|Trading|Traders|Manufacturing|Mfg|Products|Supplies|Logistics|Construction|Builders|Contractors)$', line):
            return line.strip()
        
        # If line has 2+ words with proper case, might be company
        words = line.split()
        if 2 <= len(words) <= 6 and all(w[0].isupper() or w.isupper() or w.lower() in ['and', 'of', 'the', '&', '-'] for w in words if w):
            return line.strip()
    
    return None


def _guess_source(lines: list) -> str:
    """Guess source/category only from clean category-like lines; never item lines."""
    import re
    for line in lines[:15]:
        lower = line.lower()
        if re.search(r'[£$€₹%]|\d', line):
            continue
        if any(kw in lower for kw in ['material', 'item', 'product', 'service', 'supply', 'equipment', 'labor', 'transport', 'rental', 'consulting', 'professional']):
            if ':' in line:
                value = line.split(':', 1)[1].strip()
                if _is_plausible_name(value):
                    return value
            elif re.match(r'^[A-Z][a-z]+(?:\s[A-Z][a-z]+){0,3}$', line) and _is_plausible_name(line):
                return line.strip()
    return None


def _guess_date(text: str) -> str:
    """Extract date using regex patterns."""
    import re
    # Common date patterns: YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY, DD-MMM-YYYY, etc.
    patterns = [
        r'\b(\d{4}[-/]\d{2}[-/]\d{2})\b',  # YYYY-MM-DD or YYYY/MM/DD
        r'\b(\d{2}[-/]\d{2}[-/]\d{4})\b',  # DD-MM-YYYY or MM-DD-YYYY
        r'\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b',  # 15 Sep 2026
        r'\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})\b',  # Sep 15, 2026
    ]
    
    for pattern in _DATE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return _normalize_date(match.group(1), text)

    return None


def _guess_amount(text: str) -> str:
    """Extract amount using regex patterns."""
    import re
    # Look for currency amounts
    patterns = [
        r'[₹$€£]\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',  # $1,234.56
        r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:USD|EUR|GBP|INR|₹|rs)',  # 1,234.56 USD
        r'(?:total|amount|price|cost|value)[:\s]*[₹$€£]?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',  # Total: $1,234.56
        r'\b(\d{1,3}(?:,\d{3})*(?:\.\d{2}))\b',  # 1,234.56
    ]
    
    # Prefer an explicitly labeled total/amount over any currency figure
    labeled = re.findall(r'(?:total|amount due|balance|grand total|subtotal|amount)[^0-9£$€₹\n]{0,20}[£$€₹]?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)', text, re.IGNORECASE)
    if labeled:
        return labeled[-1].replace(',', '')
    match = re.search(r'[£$€₹]\s*(\d+(?:,\d{3})*(?:\.\d{2})?)', text)
    if match:
        return match.group(1).replace(',', '')
    return None


def _clean_value(line: str) -> str:
    import re
    value = re.sub(r'^(contractor|vendor|supplier|from|source|category|type|date|invoice date|bill date|amount|total|sum)[:\s]*', '', line, flags=re.IGNORECASE)
    return value.strip()