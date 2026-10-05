import os
import json
import re
import shutil
import magic
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, Query, status
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Optional, List
from collections import defaultdict
import time

from app.database import get_db
from app.api.auth import get_current_user
from app.models import User, Contractor, Source, Invoice, InvoiceStatus, AuditLog
from app.schemas import OCRResult, ContractorResponse, SourceResponse, InvoiceFilters, InvoiceListItem
from app.services.ocr import extract_text, parse_ocr_text
from app.services.organize import process_confirm, log_audit
from app.core.config import settings
from app.core.security import decode_access_token
from app.utils.security import sanitize_ocr_text, get_relative_file_path

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DIR = BASE_DIR / "frontend" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

TEMP_STORAGE = os.path.join(settings.STORAGE_PATH, "temp")
os.makedirs(TEMP_STORAGE, exist_ok=True)

ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/bmp", "image/tiff", "image/webp",
    "application/pdf"
}

_rate_limit_store = defaultdict(list)

def check_rate_limit(client_ip: str, max_requests: int = 10, window_seconds: int = 60) -> bool:
    now = time.time()
    requests = _rate_limit_store[client_ip]
    requests[:] = [req_time for req_time in requests if now - req_time < window_seconds]
    if len(requests) >= max_requests:
        return False
    requests.append(now)
    return True

def validate_file_path(file_path: str, allowed_base: str) -> bool:
    try:
        resolved = Path(file_path).resolve()
        allowed = Path(allowed_base).resolve()
        return str(resolved).startswith(str(allowed))
    except Exception:
        return False

def validate_file_type(file_bytes: bytes) -> bool:
    mime_type = magic.from_buffer(file_bytes, mime=True)
    return mime_type in ALLOWED_MIME_TYPES


@router.post("/api/upload")
async def upload_invoice(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    client_ip = request.client.host
    if not check_rate_limit(client_ip, settings.RATE_LIMIT_REQUESTS, settings.RATE_LIMIT_WINDOW_SECONDS):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    if not validate_file_type(file_bytes):
        raise HTTPException(status_code=400, detail="Invalid file type. Only images and PDFs allowed.")

    job_id, ocr_text = extract_text(file_bytes, file.filename)

    ocr_text = sanitize_ocr_text(ocr_text)
    parsed = parse_ocr_text(ocr_text)

    # Check if extraction failed - return error instead of silently using unknown values
    contractor_name = parsed.get("contractor")
    purchased_from = parsed.get("source")
    
    if not contractor_name or not purchased_from:
        # Try to extract from filename as fallback
        if not contractor_name:
            contractor_name = os.path.splitext(file.filename)[0].replace('_', ' ')
        if not purchased_from:
            purchased_from = "Materials"
        
        # If still unknown, return extraction error
        if not contractor_name or contractor_name.lower() in ['unknown', 'unknown_contractor']:
            raise HTTPException(
                status_code=422, 
                detail="Could not extract contractor name from the invoice. Please ensure the invoice contains a clear company name or contractor label."
            )
        if not purchased_from or purchased_from.lower() in ['unknown', 'unknown_source']:
            raise HTTPException(
                status_code=422,
                detail="Could not extract source/material from the invoice. Please ensure the invoice contains a clear item description or category."
            )

    # Sanitize names for filename
    contractor_safe = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', contractor_name.strip().replace(" ", "_")).strip('._-')
    purchased_from_safe = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', purchased_from.strip().replace(" ", "_")).strip('._-')
    if not contractor_safe:
        contractor_safe = "unknown_contractor"
    if not purchased_from_safe:
        purchased_from_safe = "unknown_source"

    # Use today's date (server date)
    today_date = datetime.now().strftime("%Y-%m-%d")

    _, file_extension = os.path.splitext(file.filename)
    if not file_extension:
        file_extension = ".jpg"

    # Generate the proper filename: contractor_name_purchased_from_YYYY-MM-DD.extension
    generated_filename = f"{contractor_safe}_purchased_from_{purchased_from_safe}_{today_date}{file_extension}"

    # Save physically in the configured storage location
    invoice_date = datetime.now()
    quarter = f"Q{(invoice_date.month - 1) // 3 + 1}"
    month = invoice_date.strftime("%m_%B")
    week_num = (invoice_date.day - 1) // 7 + 1
    week = f"Week_{week_num:02d}"
    
    storage_path = os.path.join(
        settings.STORAGE_PATH,
        str(current_user.id),
        quarter,
        month,
        week
    )
    os.makedirs(storage_path, exist_ok=True)
    
    # Save with the generated filename as the final stored file
    final_path = os.path.join(storage_path, generated_filename)
    with open(final_path, "wb") as f:
        f.write(file_bytes)

    # Also save to temp for review page (with UUID for temp only)
    temp_filename = f"{job_id}_{file.filename}"
    temp_path = os.path.join(TEMP_STORAGE, temp_filename)
    with open(temp_path, "wb") as f:
        f.write(file_bytes)

    # Save OCR data to temp
    ocr_file = os.path.join(TEMP_STORAGE, f"{job_id}_ocr.json")
    with open(ocr_file, "w") as f:
        json.dump({"text": ocr_text, "parsed": parsed}, f)

    contractors = db.query(Contractor).all()
    sources = db.query(Source).all()

    return {
        "job_id": job_id,
        "filename": generated_filename,  # Return the actual saved filename, not UUID
        "original_filename": file.filename,
        "generated_filename": generated_filename,
        "extracted": {
            "contractor": contractor_name,
            "purchased_from": purchased_from,
            "date": today_date
        },
        "contractors": [{"id": c.id, "name": c.name, "short_code": c.short_code} for c in contractors],
        "sources": [{"id": s.id, "name": s.name, "short_code": s.short_code} for s in sources],
        "message": "File uploaded successfully. Please review and confirm."
    }


@router.get("/review/{job_id}", response_class=HTMLResponse)
async def review_invoice(
    request: Request,
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    temp_files = [f for f in os.listdir(TEMP_STORAGE) if f.startswith(job_id + "_") and not f.endswith("_ocr.json")]
    if not temp_files:
        raise HTTPException(status_code=404, detail="Job not found")

    temp_filename = temp_files[0]
    temp_path = os.path.join(TEMP_STORAGE, temp_filename)
    original_filename = temp_filename[len(job_id) + 1:]

    ocr_file = os.path.join(TEMP_STORAGE, f"{job_id}_ocr.json")
    if os.path.exists(ocr_file):
        with open(ocr_file, "r") as f:
            ocr_data = json.load(f)
        ocr_text = sanitize_ocr_text(ocr_data.get("text", ""))
        parsed = ocr_data.get("parsed", {})
    else:
        with open(temp_path, "rb") as f:
            file_bytes = f.read()
        _, ocr_text = extract_text(file_bytes, original_filename)
        ocr_text = sanitize_ocr_text(ocr_text)
        parsed = parse_ocr_text(ocr_text)
        with open(ocr_file, "w") as f:
            json.dump({"text": ocr_text, "parsed": parsed}, f)

    contractors = db.query(Contractor).all()
    sources = db.query(Source).all()

    # Get the generated filename from the stored file
    # The generated filename follows the pattern: contractor_purchased_from_source_YYYY-MM-DD.ext
    invoice_date = datetime.now()
    quarter = f"Q{(invoice_date.month - 1) // 3 + 1}"
    month = invoice_date.strftime("%m_%B")
    week_num = (invoice_date.day - 1) // 7 + 1
    week = f"Week_{week_num:02d}"
    
    storage_dir = os.path.join(
        settings.STORAGE_PATH,
        str(current_user.id),
        quarter,
        month,
        week
    )
    
    # Find the stored file with the generated filename
    stored_files = []
    if os.path.exists(storage_dir):
        stored_files = [f for f in os.listdir(storage_dir) if f.endswith(os.path.splitext(original_filename)[1])]
    
    generated_filename = stored_files[0] if stored_files else original_filename

    return templates.TemplateResponse("review.html", {
        "request": request,
        "job_id": job_id,
        "filename": original_filename,
        "generated_filename": generated_filename,
        "ocr_text": ocr_text,
        "parsed": parsed,
        "contractors": contractors,
        "sources": sources,
        "user": current_user
    })


@router.get("/api/temp-file/{job_id}/{filename}")
async def serve_temp_file(
    job_id: str,
    filename: str,
    current_user: User = Depends(get_current_user)
):
    safe_filename = f"{job_id}_{filename}"
    temp_path = os.path.join(TEMP_STORAGE, safe_filename)
    
    if not validate_file_path(temp_path, TEMP_STORAGE):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not os.path.exists(temp_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    ext = os.path.splitext(filename)[1].lower()
    media_type = "application/pdf" if ext == ".pdf" else "image/jpeg"
    
    return FileResponse(
        path=temp_path,
        filename=filename,
        media_type=media_type
    )


@router.post("/api/confirm")
async def confirm_invoice(
    request: Request,
    job_id: str = Form(...),
    filename: str = Form(...),
    contractor_id: int = Form(...),
    source_id: int = Form(...),
    date: str = Form(...),
    amount: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        invoice_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    try:
        invoice_amount = float(amount.replace(",", "").replace("$", "").strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid amount format")

    temp_files = [f for f in os.listdir(TEMP_STORAGE) if f.startswith(job_id + "_") and not f.endswith("_ocr.json")]
    if not temp_files:
        raise HTTPException(status_code=404, detail="Job not found")

    temp_filename = temp_files[0]
    temp_path = os.path.join(TEMP_STORAGE, temp_filename)

    if not validate_file_path(temp_path, TEMP_STORAGE):
        raise HTTPException(status_code=403, detail="Access denied")

    contractor = db.query(Contractor).filter(Contractor.id == contractor_id).first()
    source = db.query(Source).filter(Source.id == source_id).first()
    if not contractor or not source:
        raise HTTPException(status_code=400, detail="Invalid contractor or source")

    from app.schemas import ConfirmRequest
    confirm_data = ConfirmRequest(
        job_id=job_id,
        contractor_id=contractor_id,
        source_id=source_id,
        date=invoice_date.strftime("%Y-%m-%d"),
        amount=str(invoice_amount)
    )

    ocr_file = os.path.join(TEMP_STORAGE, f"{job_id}_ocr.json")
    if os.path.exists(ocr_file):
        with open(ocr_file, "r") as f:
            ocr_json = f.read()
    else:
        with open(temp_path, "rb") as f:
            file_bytes = f.read()
        _, ocr_text = extract_text(file_bytes, filename)
        ocr_text = sanitize_ocr_text(ocr_text)
        ocr_json = json.dumps({"text": ocr_text, "parsed": parse_ocr_text(ocr_text)})

    invoice = process_confirm(
        db=db,
        user_id=current_user.id,
        temp_file_path=temp_path,
        original_filename=filename,
        confirm_data=confirm_data,
        contractor_name=contractor.name,
        source_name=source.name,
        ocr_json=ocr_json
    )

    for f in os.listdir(TEMP_STORAGE):
        if f.startswith(job_id + "_"):
            file_path = os.path.join(TEMP_STORAGE, f)
            try:
                if validate_file_path(file_path, TEMP_STORAGE):
                    os.remove(file_path)
            except OSError:
                pass

    return RedirectResponse(url="/invoices", status_code=303)


def _build_invoice_query(db: Session, user_id: int, filters: InvoiceFilters):
    query = db.query(Invoice).filter(Invoice.user_id == user_id)

    if filters.contractor_id:
        query = query.filter(Invoice.contractor_id == filters.contractor_id)
    if filters.source_id:
        query = query.filter(Invoice.source_id == filters.source_id)
    if filters.date_from:
        query = query.filter(Invoice.date >= filters.date_from)
    if filters.date_to:
        query = query.filter(Invoice.date <= filters.date_to)

    query = query.order_by(Invoice.date.desc())
    return query


@router.get("/invoices", response_class=HTMLResponse)
async def invoices_page(
    request: Request,
    contractor_id: Optional[int] = Query(None),
    source_id: Optional[int] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from datetime import datetime as dt

    filters = InvoiceFilters(
        contractor_id=contractor_id,
        source_id=source_id,
        date_from=dt.strptime(date_from, "%Y-%m-%d") if date_from else None,
        date_to=dt.strptime(date_to, "%Y-%m-%d") if date_to else None,
        page=page,
        per_page=per_page
    )

    query = _build_invoice_query(db, current_user.id, filters)
    total = query.count()
    total_pages = (total + per_page - 1) // per_page

    invoices = query.offset((page - 1) * per_page).limit(per_page).all()

    invoice_items = []
    for inv in invoices:
        invoice_items.append(InvoiceListItem(
            id=inv.id,
            date=inv.date,
            amount=inv.amount,
            contractor_name=inv.contractor.name,
            contractor_short=inv.contractor.short_code,
            source_name=inv.source.name,
            source_short=inv.source.short_code,
            file_path=get_relative_file_path(inv.file_path, settings.STORAGE_PATH),
            status=inv.status.value,
            created_at=inv.created_at
        ))

    contractors = db.query(Contractor).all()
    sources = db.query(Source).all()

    return templates.TemplateResponse("list.html", {
        "request": request,
        "invoices": invoice_items,
        "contractors": contractors,
        "sources": sources,
        "selected_contractor": contractor_id,
        "selected_source": source_id,
        "date_from": date_from,
        "date_to": date_to,
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page,
        "total": total,
        "user": current_user
    })


@router.get("/invoices/table", response_class=HTMLResponse)
async def invoices_table(
    request: Request,
    contractor_id: Optional[int] = Query(None),
    source_id: Optional[int] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from datetime import datetime as dt

    filters = InvoiceFilters(
        contractor_id=contractor_id,
        source_id=source_id,
        date_from=dt.strptime(date_from, "%Y-%m-%d") if date_from else None,
        date_to=dt.strptime(date_to, "%Y-%m-%d") if date_to else None,
        page=page,
        per_page=per_page
    )

    query = _build_invoice_query(db, current_user.id, filters)
    total = query.count()
    total_pages = (total + per_page - 1) // per_page

    invoices = query.offset((page - 1) * per_page).limit(per_page).all()

    invoice_items = []
    for inv in invoices:
        invoice_items.append(InvoiceListItem(
            id=inv.id,
            date=inv.date,
            amount=inv.amount,
            contractor_name=inv.contractor.name,
            contractor_short=inv.contractor.short_code,
            source_name=inv.source.name,
            source_short=inv.source.short_code,
            file_path=get_relative_file_path(inv.file_path, settings.STORAGE_PATH),
            status=inv.status.value,
            created_at=inv.created_at
        ))

    return templates.TemplateResponse("partials/invoice_table.html", {
        "request": request,
        "invoices": invoice_items,
        "page": page,
        "total_pages": total_pages,
        "selected_contractor": contractor_id,
        "selected_source": source_id,
        "date_from": date_from,
        "date_to": date_to,
        "per_page": per_page,
        "total": total
    })


@router.get("/api/invoices")
async def invoices_api(
    contractor_id: Optional[int] = Query(None),
    source_id: Optional[int] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from datetime import datetime as dt

    filters = InvoiceFilters(
        contractor_id=contractor_id,
        source_id=source_id,
        date_from=dt.strptime(date_from, "%Y-%m-%d") if date_from else None,
        date_to=dt.strptime(date_to, "%Y-%m-%d") if date_to else None,
        page=page,
        per_page=per_page
    )

    query = _build_invoice_query(db, current_user.id, filters)
    total = query.count()
    total_pages = (total + per_page - 1) // per_page

    invoices = query.offset((page - 1) * per_page).limit(per_page).all()

    return {
        "invoices": [
            {
                "id": inv.id,
                "date": inv.date.isoformat(),
                "amount": str(inv.amount),
                "contractor": inv.contractor.name,
                "contractor_short": inv.contractor.short_code,
                "source": inv.source.name,
                "source_short": inv.source.short_code,
                "file_path": get_relative_file_path(inv.file_path, settings.STORAGE_PATH),
                "status": inv.status.value,
                "created_at": inv.created_at.isoformat()
            }
            for inv in invoices
        ],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages
        }
    }


@router.get("/invoices/stats")
async def invoices_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    total_invoices = db.query(Invoice).filter(Invoice.user_id == current_user.id).count()
    confirmed = db.query(Invoice).filter(
        Invoice.user_id == current_user.id,
        Invoice.status == InvoiceStatus.CONFIRMED
    ).count()
    pending = db.query(Invoice).filter(
        Invoice.user_id == current_user.id,
        Invoice.status == InvoiceStatus.PENDING
    ).count()

    total_amount = db.query(func.sum(Invoice.amount)).filter(
        Invoice.user_id == current_user.id
    ).scalar() or 0

    return {
        "total_invoices": total_invoices,
        "confirmed": confirmed,
        "pending": pending,
        "total_amount": float(total_amount)
    }


@router.get("/contractors", response_model=List[ContractorResponse])
async def get_contractors(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(Contractor).all()


@router.get("/sources", response_model=List[SourceResponse])
async def get_sources(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(Source).all()


@router.get("/invoices/{invoice_id}/download")
async def download_invoice(
    invoice_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.user_id == current_user.id
    ).first()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if not os.path.exists(invoice.file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    if not validate_file_path(invoice.file_path, settings.STORAGE_PATH):
        raise HTTPException(status_code=403, detail="Access denied")

    filename = os.path.basename(invoice.file_path)
    return FileResponse(
        path=invoice.file_path,
        filename=filename,
        media_type="application/octet-stream"
    )


@router.get("/api/invoice-file/{invoice_id}")
async def get_invoice_file(
    invoice_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.user_id == current_user.id
    ).first()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if not os.path.exists(invoice.file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    if not validate_file_path(invoice.file_path, settings.STORAGE_PATH):
        raise HTTPException(status_code=403, detail="Access denied")

    ext = os.path.splitext(invoice.file_path)[1].lower()
    media_type = "application/pdf" if ext == ".pdf" else "image/jpeg"

    log_audit(
        db=db,
        user_id=current_user.id,
        action="download",
        entity_type="invoice",
        entity_id=invoice.id,
        details=f"Downloaded invoice file"
    )

    return FileResponse(
        path=invoice.file_path,
        filename=os.path.basename(invoice.file_path),
        media_type=media_type
    )