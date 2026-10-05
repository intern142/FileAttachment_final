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
    
    # First pass: look for explicit labels
    for line in lines:
        lower = line.lower()
        
        # Contractor extraction
        if any(kw in lower for kw in ["contractor", "vendor", "supplier", "from:", "billed by", "sold by", "company:"]):
            result["contractor"] = _extract_value_after_colon(line)
        
        # Source/purchased_from extraction
        elif any(kw in lower for kw in ["source", "category", "type:", "material", "purchased from", "item:", "description:"]):
            result["source"] = _extract_value_after_colon(line)
        
        # Date extraction
        elif any(kw in lower for kw in ["date", "invoice date", "bill date", "dated:", "issued:", "due date:"]):
            result["date"] = _extract_value_after_colon(line)
        
        # Amount extraction
        elif any(kw in lower for kw in ["amount", "total", "sum", "₹", "$", "rs", "usd", "price", "cost", "value:"]):
            result["amount"] = _extract_value_after_colon(line)
    
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


def _extract_value_after_colon(line: str) -> str:
    """Extract value after the first colon."""
    if ':' in line:
        return line.split(':', 1)[1].strip()
    return line.strip()


def _guess_company_name(lines: list) -> str:
    """Guess company name from first non-empty lines that look like a company name."""
    import re
    for line in lines[:10]:  # Check first 10 lines
        # Skip common non-company lines
        lower = line.lower()
        if any(skip in lower for skip in ['invoice', 'bill', 'receipt', 'date', 'total', 'amount', 'tax', 'vat', 'gst', 'no.', 'number', 'page', 'tel', 'phone', 'fax', 'email', 'www', 'http']):
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
    """Guess source/category from lines containing item descriptions."""
    import re
    # Look for item descriptions or categories
    for line in lines[:15]:
        lower = line.lower()
        if any(kw in lower for kw in ['material', 'item', 'product', 'service', 'supply', 'equipment', 'labor', 'transport', 'rental', 'consulting', 'professional']):
            # Extract the category
            if ':' in line:
                return line.split(':', 1)[1].strip()
            elif re.match(r'^[A-Z][a-z]+(?:\s[A-Z][a-z]+)*$', line):
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
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group(1)
            # Try to normalize to YYYY-MM-DD
            try:
                from datetime import datetime
                if re.match(r'\d{4}[-/]\d{2}[-/]\d{2}', date_str):
                    return date_str.replace('/', '-')
                elif re.match(r'\d{2}[-/]\d{2}[-/]\d{4}', date_str):
                    # Try both DD-MM-YYYY and MM-DD-YYYY
                    parts = date_str.replace('/', '-').split('-')
                    if len(parts) == 3:
                        # Assume DD-MM-YYYY if day > 12, else MM-DD-YYYY
                        if int(parts[0]) > 12:
                            return f"{parts[2]}-{parts[1]}-{parts[0]}"
                        else:
                            return f"{parts[2]}-{parts[0]}-{parts[1]}"
            except:
                return date_str
    
    return None


def _guess_amount(text: str) -> str:
    """Extract amount using regex patterns."""
    import re
    # Look for currency amounts
    patterns = [
        r'[₹$€£]\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',  # $1,234.56
        r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:USD|EUR|GBP|INR|₹|rs)',  # 1,234.56 USD
        r'(?:total|amount|price|cost|value)[:\s]*[₹$€£]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',  # Total: $1,234.56
        r'\b(\d{1,3}(?:,\d{3})*(?:\.\d{2}))\b',  # 1,234.56
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).replace(',', '')
    
    return None


def _clean_value(line: str) -> str:
    import re
    value = re.sub(r'^(contractor|vendor|supplier|from|source|category|type|date|invoice date|bill date|amount|total|sum)[:\s]*', '', line, flags=re.IGNORECASE)
    return value.strip()