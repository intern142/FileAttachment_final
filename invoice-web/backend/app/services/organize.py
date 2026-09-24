import os
import re
import shutil
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from sqlalchemy.orm import Session

from ..models import Invoice, InvoiceStatus, AuditLog, Contractor, Source
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


def get_or_create_contractor(db: Session, name: str) -> Contractor:
    """Match an existing contractor by name (case-insensitive) or create one."""
    clean = sanitize_filename_part(name)
    existing = db.query(Contractor).filter(
        Contractor.name.ilike(clean) if clean != "UNKNOWN" else Contractor.name == "UNKNOWN"
    ).first()
    if existing:
        return existing
    short = "".join(re.findall(r"[A-Za-z0-9]+", clean)).upper()[:10] or "UNKNOWN"
    contractor = Contractor(name=clean, short_code=short)
    db.add(contractor)
    db.commit()
    db.refresh(contractor)
    return contractor


def get_default_source(db: Session) -> Source:
    source = db.query(Source).filter(Source.short_code == "WA").first()
    if source:
        return source
    return db.query(Source).first()


def record_extracted_invoice(
    db: Session,
    user_id: int,
    contractor: str,
    invoice_date: datetime,
    file_path: str,
    ocr_json: str = None,
) -> Invoice:
    """Create an Invoice row so the extracted file has a stable invoice_id."""
    contractor_obj = get_or_create_contractor(db, contractor)
    source_obj = get_default_source(db)
    invoice = Invoice(
        user_id=user_id,
        contractor_id=contractor_obj.id,
        source_id=source_obj.id,
        date=invoice_date,
        amount=Decimal("0"),
        file_path=file_path,
        ocr_json=ocr_json,
        status=InvoiceStatus.pending,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


def rename_extracted_invoice_file(
    db: Session,
    invoice: Invoice,
    new_contractor: str,
    new_purchased_from: str,
) -> str:
    """Rename the stored file on disk to CONTRACTOR--PURCHASED_FROM--DATE.ext and update metadata."""
    old_path = invoice.file_path
    if not os.path.exists(old_path):
        raise FileNotFoundError(f"File not found on disk: {old_path}")

    ext = os.path.splitext(old_path)[1] or ".jpg"
    directory = os.path.dirname(old_path)
    new_dest = os.path.join(
        directory,
        build_invoice_filename(new_contractor, new_purchased_from, invoice.date),
    )
    new_path = f"{new_dest}{ext}"
    counter = 1
    while os.path.exists(new_path) and os.path.realpath(new_path) != os.path.realpath(old_path):
        new_path = f"{new_dest}_{counter}{ext}"
        counter += 1

    os.rename(old_path, new_path)

    invoice.file_path = new_path
    db.commit()
    db.refresh(invoice)
    return new_path


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