import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session

from ..models import Invoice, InvoiceStatus, AuditLog
from ..schemas import ConfirmRequest
from ..core.config import get_settings

settings = get_settings()


def generate_storage_path(
    user_id: int,
    contractor_short: str,
    source_short: str,
    invoice_date: datetime
) -> str:
    quarter = f"Q{(invoice_date.month - 1) // 3 + 1}"
    month = invoice_date.strftime("%m_%B")
    week_num = (invoice_date.day - 1) // 7 + 1
    week = f"Week_{week_num:02d}"
    filename = f"{contractor_short}-{source_short}-{invoice_date.strftime('%Y%m%d')}"
    return os.path.join(
        settings.storage_path,
        str(user_id),
        quarter,
        month,
        week,
        filename
    )


def ensure_directory(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def move_file_to_storage(temp_path: str, dest_path: str, extension: str) -> str:
    ensure_directory(os.path.dirname(dest_path))
    final_path = f"{dest_path}{extension}"
    shutil.move(temp_path, final_path)
    return final_path


def sanitize_filename_part(value: str) -> str:
    """Make an extracted name safe for use as a filename part."""
    text = str(value or "").strip()
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", text)
    text = re.sub(r"-{2,}", "-", text)  # keep the "--" separator unambiguous
    text = re.sub(r"\s+", " ", text).strip(" .-")
    return text or "UNKNOWN"


def build_invoice_filename(
    contractor: str,
    purchased_from: str,
    invoice_date: datetime,
) -> str:
    """CONTRACTOR--PURCHASED_FROM--YYYY-MM-DD(ext applied later)."""
    date_part = invoice_date.strftime("%Y-%m-%d")
    return (
        f"{sanitize_filename_part(contractor)}"
        f"--{sanitize_filename_part(purchased_from)}"
        f"--{date_part}"
    )


def generate_extracted_storage_path(
    user_id: int,
    contractor: str,
    purchased_from: str,
    invoice_date: datetime,
) -> str:
    quarter = f"Q{(invoice_date.month - 1) // 3 + 1}"
    month = invoice_date.strftime("%m_%B")
    week_num = (invoice_date.day - 1) // 7 + 1
    week = f"Week_{week_num:02d}"
    filename = build_invoice_filename(contractor, purchased_from, invoice_date)
    return os.path.join(
        settings.storage_path,
        str(user_id),
        quarter,
        month,
        week,
        filename,
    )


def save_extracted_invoice(
    user_id: int,
    contractor: str,
    purchased_from: str,
    invoice_date: datetime,
    extension: str,
    content: bytes,
) -> str:
    """Save the extracted invoice to storage using the CONTRACTOR--PURCHASED_FROM--DATE name."""
    dest = generate_extracted_storage_path(user_id, contractor, purchased_from, invoice_date)
    ensure_directory(os.path.dirname(dest))
    final_path = f"{dest}{extension}"
    counter = 1
    while os.path.exists(final_path):
        final_path = f"{dest}_{counter}{extension}"
        counter += 1
    with open(final_path, "wb") as f:
        f.write(content)
    return final_path


def save_invoice(
    db: Session,
    user_id: int,
    contractor_id: int,
    source_id: int,
    invoice_date: datetime,
    amount: float,
    file_path: str,
    ocr_json: str = None
) -> Invoice:
    invoice = Invoice(
        user_id=user_id,
        contractor_id=contractor_id,
        source_id=source_id,
        date=invoice_date,
        amount=amount,
        file_path=file_path,
        ocr_json=ocr_json,
        status=InvoiceStatus.confirmed
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


def log_audit(
    db: Session,
    user_id: int,
    action: str,
    entity_type: str,
    entity_id: int = None,
    details: str = None
) -> AuditLog:
    audit = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details
    )
    db.add(audit)
    db.commit()
    return audit


def process_confirm(
    db: Session,
    user_id: int,
    temp_file_path: str,
    original_filename: str,
    confirm_data: ConfirmRequest,
    contractor_short: str,
    source_short: str,
    ocr_json: str = None
) -> Invoice:
    _, ext = os.path.splitext(original_filename)
    dest_path = generate_storage_path(user_id, contractor_short, source_short, confirm_data.date)
    final_path = move_file_to_storage(temp_file_path, dest_path, ext)
    invoice = save_invoice(
        db=db,
        user_id=user_id,
        contractor_id=confirm_data.contractor_id,
        source_id=confirm_data.source_id,
        invoice_date=confirm_data.date,
        amount=float(confirm_data.amount),
        file_path=final_path,
        ocr_json=ocr_json
    )
    log_audit(
        db=db,
        user_id=user_id,
        action="confirm",
        entity_type="invoice",
        entity_id=invoice.id,
        details=f"Confirmed invoice from {original_filename}"
    )
    return invoice