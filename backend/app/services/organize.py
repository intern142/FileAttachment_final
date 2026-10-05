import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session

from app.models import Invoice, InvoiceStatus, AuditLog
from app.schemas import ConfirmRequest
from app.core.config import settings


def sanitize_filename_part(value: str) -> str:
    """Sanitize a filename part to be safe for filesystem."""
    if not value:
        return "unknown"
    # Replace spaces with underscores
    value = value.strip().replace(" ", "_")
    # Remove any characters that are not alphanumeric, underscore, hyphen, or dot
    value = re.sub(r'[^a-zA-Z0-9_\-\.]', '', value)
    # Remove any leading/trailing dots or hyphens
    value = value.strip('.-')
    # Ensure not empty
    if not value:
        return "unknown"
    # Limit length
    return value[:100]


def generate_storage_path(
    user_id: int,
    contractor_name: str,
    source_name: str,
    invoice_date: datetime
) -> str:
    """Generate storage path with format: contractor_name_purchased_from_YYYY-MM-DD"""
    contractor_safe = sanitize_filename_part(contractor_name)
    source_safe = sanitize_filename_part(source_name)
    
    # Handle both datetime and string date formats
    if isinstance(invoice_date, str):
        try:
            invoice_date = datetime.strptime(invoice_date, "%Y-%m-%d")
        except ValueError:
            invoice_date = datetime.now()
    
    date_str = invoice_date.strftime("%Y-%m-%d")
    filename = f"{contractor_safe}_{source_safe}_{date_str}"
    
    quarter = f"Q{(invoice_date.month - 1) // 3 + 1}"
    month = invoice_date.strftime("%m_%B")
    week_num = (invoice_date.day - 1) // 7 + 1
    week = f"Week_{week_num:02d}"
    
    return os.path.join(
        settings.STORAGE_PATH,
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
        status=InvoiceStatus.CONFIRMED
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


def log_audit(
    db: Session,
    user_id: int,
    action: str,
    entity_id: int = None,
    details: str = None
) -> AuditLog:
    audit = AuditLog(
        user_id=user_id,
        action=action,
        invoice_id=entity_id,
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
    contractor_name: str,
    source_name: str,
    ocr_json: str = None
) -> Invoice:
    _, ext = os.path.splitext(original_filename)
    dest_path = generate_storage_path(user_id, contractor_name, source_name, confirm_data.date)
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
        entity_id=invoice.id,
        details=f"Confirmed invoice from {original_filename}"
    )
    return invoice