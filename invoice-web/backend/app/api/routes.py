import os
import io
import uuid
import json
import shutil
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from math import ceil

try:
    import pytesseract
    from pdf2image import convert_from_bytes
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

from ..database import get_db
from ..models import User, Contractor, Source, Invoice, InvoiceStatus
from ..schemas import (
    InvoiceOut, InvoiceListParams, ConfirmRequest, ContractorOut, SourceOut, OCRResult
)
from ..services.organize import process_confirm
from ..api.auth import get_current_user
from ..core.config import get_settings

settings = get_settings()
router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")

TEMP_DIR = "/tmp/invoice_uploads"
os.makedirs(TEMP_DIR, exist_ok=True)


def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    if not OCR_AVAILABLE:
        return "OCR not available - pytesseract/pdf2image not installed"
    ext = os.path.splitext(filename)[1].lower()
    try:
        if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']:
            image = Image.open(io.BytesIO(file_bytes))
            return pytesseract.image_to_string(image)
        elif ext == '.pdf':
            images = convert_from_bytes(file_bytes)
            text = ""
            for img in images:
                text += pytesseract.image_to_string(img) + "\n"
            return text
        else:
            return f"Unsupported file type: {ext}"
    except Exception as e:
        return f"OCR error: {str(e)}"


import io


@router.post("/api/upload")
async def upload_invoice(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    job_id = str(uuid.uuid4())[:8]
    ext = os.path.splitext(file.filename)[1]
    temp_filename = f"{job_id}_{file.filename}"
    temp_path = os.path.join(TEMP_DIR, temp_filename)
    content = await file.read()
    with open(temp_path, "wb") as f:
        f.write(content)
    ocr_text = extract_text_from_file(content, file.filename)
    ocr_data = {
        "text": ocr_text,
        "contractor": None,
        "source": None,
        "date": None,
        "amount": None
    }
    lines = ocr_text.split('\n')
    for line in lines:
        line_lower = line.lower()
        if any(kw in line_lower for kw in ['contractor', 'vendor', 'supplier']):
            ocr_data['contractor'] = line.strip()
        if any(kw in line_lower for kw in ['source', 'channel', 'via']):
            ocr_data['source'] = line.strip()
        if any(kw in line_lower for kw in ['date', 'invoice date']):
            ocr_data['date'] = line.strip()
        if any(kw in line_lower for kw in ['amount', 'total', 'sum']):
            ocr_data['amount'] = line.strip()
    ocr_file = os.path.join(TEMP_DIR, f"{job_id}_ocr.json")
    with open(ocr_file, "w") as f:
        json.dump(ocr_data, f)
    return OCRResult(job_id=job_id, **ocr_data)


@router.get("/review/{job_id}", response_class=HTMLResponse)
async def review_invoice(
    request: Request,
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    ocr_file = os.path.join(TEMP_DIR, f"{job_id}_ocr.json")
    if not os.path.exists(ocr_file):
        raise HTTPException(status_code=404, detail="Review session expired")
    with open(ocr_file) as f:
        ocr_data = json.load(f)
    temp_files = [f for f in os.listdir(TEMP_DIR) if f.startswith(job_id) and not f.endswith('_ocr.json')]
    if not temp_files:
        raise HTTPException(status_code=404, detail="Upload session expired")
    image_url = f"/api/temp-file/{temp_files[0]}"
    contractors = db.query(Contractor).all()
    sources = db.query(Source).all()
    return templates.TemplateResponse("review.html", {
        "request": request,
        "job_id": job_id,
        "image_url": image_url,
        "extracted": ocr_data,
        "ocr_text": ocr_data.get("text", ""),
        "contractors": contractors,
        "sources": sources
    })


@router.get("/api/temp-file/{filename}")
async def serve_temp_file(filename: str):
    file_path = os.path.join(TEMP_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


@router.post("/confirm", response_model=InvoiceOut)
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
    temp_files = [f for f in os.listdir(temp_dir) if f.startswith(job_id)]
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
    return invoice


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