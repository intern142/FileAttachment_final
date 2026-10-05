import os
import io
import uuid
import json
import re
import shutil
import time
import magic
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, Query
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from math import ceil
from PIL import Image

from ..database import get_db
from ..models import User, Contractor, Source, Invoice, InvoiceStatus
from ..schemas import (
    InvoiceOut, InvoiceListParams, ConfirmRequest, ContractorOut, SourceOut, OCRResult,
    ExtractResult, RenameRequest, RenameResult,
)
from ..services.organize import (
    process_confirm,
    save_extracted_invoice,
    record_extracted_invoice,
    rename_extracted_invoice_file,
)
from ..services.extraction import (
    extract_text_from_file,
    extract_invoice_fields,
    has_ocr_error,
    SUPPORTED_EXTENSIONS,
)
from .auth import get_current_user
from ..core.config import settings

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

TEMP_DIR = "/tmp/invoice_uploads"
os.makedirs(TEMP_DIR, exist_ok=True)

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
        resolved = os.path.realpath(file_path)
        allowed = os.path.realpath(allowed_base)
        return resolved.startswith(allowed)
    except Exception:
        return False


def validate_file_type(file_bytes: bytes) -> bool:
    mime_type = magic.from_buffer(file_bytes, mime=True)
    return mime_type in ALLOWED_MIME_TYPES


def normalize_extension(filename: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext in (".jpeg", ".tif"):
        return ".jpg" if ext == ".jpeg" else ".tiff"
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Allowed: JPG, JPEG, PNG, PDF",
        )
    return ext


def sanitize_ocr_text(text: str) -> str:
    if not text:
        return ""
    lines = text.split('\n')
    sanitized = []
    for line in lines:
        line = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', line)
        sanitized.append(line)
    return '\n'.join(sanitized)


@router.post("/api/upload", response_model=ExtractResult)
async def upload_invoice(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    client_ip = request.client.host
    if not check_rate_limit(client_ip, settings.RATE_LIMIT_REQUESTS if hasattr(settings, 'RATE_LIMIT_REQUESTS') else 10, 
                            settings.RATE_LIMIT_WINDOW_SECONDS if hasattr(settings, 'RATE_LIMIT_WINDOW_SECONDS') else 60):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    if not validate_file_type(file_bytes):
        raise HTTPException(status_code=400, detail="Invalid file type. Only images and PDFs allowed.")

    ext = normalize_extension(file.filename)
    ocr_text = extract_text_from_file(file_bytes, file.filename)
    ocr_text = sanitize_ocr_text(ocr_text)
    if has_ocr_error(ocr_text):
        raise HTTPException(status_code=422, detail=ocr_text)
    fields = extract_invoice_fields(ocr_text)
    try:
        img = Image.open(io.BytesIO(file_bytes))
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        jpg_bytes = io.BytesIO()
        img.save(jpg_bytes, format="JPEG", quality=95)
        content = jpg_bytes.getvalue()
        ext = ".jpg"
    except Exception:
        content = file_bytes
    today = date.today()
    saved_path = save_extracted_invoice(
        user_id=current_user.id,
        contractor=fields["contractor"],
        purchased_from=fields["purchased_from"],
        invoice_date=today,
        extension=ext,
        content=content,
    )
    invoice = record_extracted_invoice(
        db=db,
        user_id=current_user.id,
        contractor=fields["contractor"],
        invoice_date=today,
        file_path=saved_path,
        ocr_json=ocr_text,
    )
    return ExtractResult(
        contractor=fields["contractor"],
        purchased_from=fields["purchased_from"],
        date=today.strftime("%Y-%m-%d"),
        filename=os.path.basename(saved_path),
        invoice_id=invoice.id,
        saved=True,
    )


@router.get("/review/{job_id}", response_class=HTMLResponse)
async def review_invoice(
    request: Request,
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        ocr_file = os.path.join(TEMP_DIR, f"{job_id}_ocr.json")
        if not os.path.exists(ocr_file):
            raise HTTPException(status_code=404, detail="Review session expired")
        with open(ocr_file) as f:
            ocr_data = json.load(f)
        temp_files = [f for f in os.listdir(TEMP_DIR) if f.startswith(job_id) and not f.endswith('_ocr.json')]
        if not temp_files:
            raise HTTPException(status_code=404, detail="Upload session expired")
        image_url = f"/api/temp-file/{job_id}/{temp_files[0].replace(f'{job_id}_', '')}"
        contractors = db.query(Contractor).all()
        sources = db.query(Source).all()
        return templates.TemplateResponse("review.html", {
            "request": request,
            "job_id": job_id,
            "image_url": image_url,
            "extracted": ocr_data,
            "contractors": contractors,
            "sources": sources
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/api/temp-file/{job_id}/{filename}")
async def serve_temp_file(
    job_id: str,
    filename: str,
    current_user: User = Depends(get_current_user)
):
    safe_filename = f"{job_id}_{filename}"
    temp_path = os.path.join(TEMP_DIR, safe_filename)
    
    if not validate_file_path(temp_path, TEMP_DIR):
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


def _parse_extracted_filename(filename: str) -> dict:
    base = os.path.splitext(filename)[0]
    parts = base.split("--")
    if len(parts) >= 3:
        return {
            "contractor": parts[0],
            "purchased_from": parts[1],
            "date": parts[2],
        }
    return {"contractor": "", "purchased_from": "", "date": ""}


@router.get("/api/extracted-files")
def list_extracted_files(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    root = os.path.join(settings.STORAGE_PATH, str(current_user.id))
    results = []
    invoice_by_path = {}
    for inv in db.query(Invoice).filter(Invoice.user_id == current_user.id).all():
        if inv.file_path:
            invoice_by_path[os.path.realpath(inv.file_path)] = inv.id
    if os.path.isdir(root):
        for dirpath, _, filenames in os.walk(root):
            for name in filenames:
                if name.startswith(".") or name.lower().endswith(".json"):
                    continue
                full = os.path.join(dirpath, name)
                parsed = _parse_extracted_filename(name)
                results.append({
                    "filename": name,
                    "path": os.path.relpath(full, settings.STORAGE_PATH),
                    "saved_at": datetime.fromtimestamp(os.path.getmtime(full)).isoformat(),
                    "invoice_id": invoice_by_path.get(os.path.realpath(full)),
                    **parsed,
                })
    results.sort(key=lambda r: r["saved_at"], reverse=True)
    return results


@router.get("/api/extracted-file")
def download_extracted_file(
    path: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    storage_root = os.path.realpath(settings.STORAGE_PATH)
    user_root = os.path.realpath(os.path.join(storage_root, str(current_user.id)))
    full = os.path.realpath(os.path.join(storage_root, path))
    if not full.startswith(user_root + os.sep):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(full, filename=os.path.basename(full))


@router.post("/api/rename-file", response_model=RenameResult)
def rename_file(
    payload: RenameRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invoice = db.query(Invoice).filter(
        Invoice.id == payload.invoice_id,
        Invoice.user_id == current_user.id,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    new_contractor = sanitize_value(payload.contractor) or "UNKNOWN"
    new_purchased = sanitize_value(payload.purchased_from) or "UNKNOWN"

    try:
        new_path = rename_extracted_invoice_file(
            db=db,
            invoice=invoice,
            new_contractor=new_contractor,
            new_purchased_from=new_purchased,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to rename file: {e}")

    rel_path = os.path.relpath(new_path, settings.STORAGE_PATH)
    return RenameResult(
        invoice_id=invoice.id,
        filename=os.path.basename(new_path),
        path=rel_path,
        url=f"/api/extracted-file?path={rel_path}",
        saved=True,
    )


def sanitize_value(value: str) -> str:
    return (value or "").strip()


@router.delete("/api/extracted-file")
def delete_extracted_file(
    invoice_id: Optional[int] = Query(None),
    path: str = Query(default=""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    full = None
    if invoice_id is not None:
        invoice = db.query(Invoice).filter(
            Invoice.id == invoice_id,
            Invoice.user_id == current_user.id,
        ).first()
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")
        full = invoice.file_path
    else:
        storage_root = os.path.realpath(settings.STORAGE_PATH)
        user_root = os.path.realpath(os.path.join(storage_root, str(current_user.id)))
        full = os.path.realpath(os.path.join(storage_root, path))
        if not full.startswith(user_root + os.sep):
            raise HTTPException(status_code=403, detail="Forbidden")
        invoice = db.query(Invoice).filter(
            Invoice.user_id == current_user.id,
            Invoice.file_path.isnot(None),
        ).all()
        for inv in invoice:
            if os.path.realpath(inv.file_path) == full:
                invoice = inv
                break
        else:
            invoice = None

    if not full or not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        os.remove(full)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {e}")
    if invoice is not None:
        db.delete(invoice)
        db.commit()
    return {"deleted": True, "filename": os.path.basename(full)}


@router.post("/confirm")
async def confirm_invoice(
    request: Request,
    job_id: str = Form(...),
    contractor_id: int = Form(...),
    source_id: int = Form(...),
    date: str = Form(...),
    amount: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    temp_dir = "/tmp/invoice_uploads"
    temp_files = [f for f in os.listdir(temp_dir) if f.startswith(job_id) and not f.endswith('_ocr.json')]
    if not temp_files:
        raise HTTPException(status_code=404, detail="Upload session expired")
    temp_file_path = os.path.join(temp_dir, temp_files[0])
    original_filename = temp_files[0].replace(f"{job_id}_", "")
    invoice_date = datetime.strptime(date, "%Y-%m-%d")
    contractor = db.query(Contractor).filter(Contractor.id == contractor_id).first()
    source = db.query(Source).filter(Source.id == source_id).first()
    if not contractor or not source:
        raise HTTPException(status_code=400, detail="Invalid contractor or source")
    confirm_data = ConfirmRequest(
        job_id=job_id,
        contractor_id=contractor_id,
        source_id=source_id,
        date=invoice_date,
        amount=Decimal(amount)
    )
    ocr_json = None
    ocr_file = os.path.join(temp_dir, f"{job_id}_ocr.json")
    if os.path.exists(ocr_file):
        with open(ocr_file) as f:
            ocr_json = f.read()
    invoice = process_confirm(
        db=db,
        user_id=current_user.id,
        temp_file_path=temp_file_path,
        original_filename=original_filename,
        confirm_data=confirm_data,
        contractor_short=contractor.short_code,
        source_short=source.short_code,
        ocr_json=ocr_json
    )
    for f in os.listdir(temp_dir):
        if f.startswith(job_id):
            try:
                os.remove(os.path.join(temp_dir, f))
            except:
                pass
    return RedirectResponse(url="/", status_code=303)


@router.get("/invoices", response_model=List[InvoiceOut])
def list_invoices(
    params: InvoiceListParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Invoice).filter(Invoice.user_id == current_user.id)
    if params.contractor_id:
        query = query.filter(Invoice.contractor_id == params.contractor_id)
    if params.source_id:
        query = query.filter(Invoice.source_id == params.source_id)
    if params.date_from:
        query = query.filter(Invoice.date >= params.date_from)
    if params.date_to:
        query = query.filter(Invoice.date <= params.date_to)
    query = query.order_by(Invoice.date.desc())
    total = query.count()
    offset = (params.page - 1) * params.page_size
    invoices = query.offset(offset).limit(params.page_size).all()
    for inv in invoices:
        inv.contractor = inv.contractor
        inv.source = inv.source
    return invoices


@router.get("/invoices/stats")
def get_invoice_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    total = db.query(Invoice).filter(Invoice.user_id == current_user.id).count()
    total_amount = db.query(func.sum(Invoice.amount)).filter(Invoice.user_id == current_user.id).scalar() or 0
    return {"total_invoices": total, "total_amount": float(total_amount)}


@router.get("/contractors", response_model=List[ContractorOut])
def list_contractors(db: Session = Depends(get_db)):
    return db.query(Contractor).all()


@router.get("/sources", response_model=List[SourceOut])
def list_sources(db: Session = Depends(get_db)):
    return db.query(Source).all()


@router.get("/invoices/{invoice_id}/download")
def download_invoice(
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
    return FileResponse(
        path=invoice.file_path,
        filename=os.path.basename(invoice.file_path),
        media_type="application/octet-stream"
    )


@router.get("/invoices/page", response_class=HTMLResponse)
def invoices_page(
    request: Request,
    contractor_id: Optional[int] = Query(None),
    source_id: Optional[int] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    contractors = db.query(Contractor).all()
    sources = db.query(Source).all()
    query = db.query(Invoice).filter(Invoice.user_id == current_user.id)
    if contractor_id:
        query = query.filter(Invoice.contractor_id == contractor_id)
    if source_id:
        query = query.filter(Invoice.source_id == source_id)
    if date_from:
        query = query.filter(Invoice.date >= datetime.strptime(date_from, "%Y-%m-%d"))
    if date_to:
        query = query.filter(Invoice.date <= datetime.strptime(date_to, "%Y-%m-%d"))
    query = query.order_by(Invoice.date.desc())
    total = query.count()
    total_pages = ceil(total / page_size) if total > 0 else 1
    offset = (page - 1) * page_size
    invoices = query.offset(offset).limit(page_size).all()
    pagination = {
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "page_size": page_size
    }
    return templates.TemplateResponse("list.html", {
        "request": request,
        "invoices": invoices,
        "contractors": contractors,
        "sources": sources,
        "selected_contractor": contractor_id,
        "selected_source": source_id,
        "date_from": date_from,
        "date_to": date_to,
        "pagination": pagination
    })


@router.get("/invoices/table", response_class=HTMLResponse)
def invoices_table(
    request: Request,
    contractor_id: Optional[int] = Query(None),
    source_id: Optional[int] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    contractors = db.query(Contractor).all()
    sources = db.query(Source).all()
    query = db.query(Invoice).filter(Invoice.user_id == current_user.id)
    if contractor_id:
        query = query.filter(Invoice.contractor_id == contractor_id)
    if source_id:
        query = query.filter(Invoice.source_id == source_id)
    if date_from:
        query = query.filter(Invoice.date >= datetime.strptime(date_from, "%Y-%m-%d"))
    if date_to:
        query = query.filter(Invoice.date <= datetime.strptime(date_to, "%Y-%m-%d"))
    query = query.order_by(Invoice.date.desc())
    total = query.count()
    total_pages = ceil(total / page_size) if total > 0 else 1
    offset = (page - 1) * page_size
    invoices = query.offset(offset).limit(page_size).all()
    pagination = {
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "page_size": page_size
    }
    return templates.TemplateResponse("partials/invoice_table.html", {
        "request": request,
        "invoices": invoices,
        "contractors": contractors,
        "sources": sources,
        "selected_contractor": contractor_id,
        "selected_source": source_id,
        "date_from": date_from,
        "date_to": date_to,
        "pagination": pagination
    })