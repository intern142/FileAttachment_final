import os
import json
import shutil
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, Query
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Optional, List

from app.database import get_db
from app.api.auth import get_current_user
from app.models import User, Contractor, Source, Invoice, InvoiceStatus, AuditLog
from app.schemas import OCRResult, ContractorResponse, SourceResponse, InvoiceFilters, InvoiceListItem
from app.services.ocr import extract_text, parse_ocr_text
from app.services.organize import process_confirm
from app.core.config import settings

router = APIRouter()

templates = Jinja2Templates(directory="frontend/templates")

TEMP_STORAGE = os.path.join(settings.STORAGE_PATH, "temp")
os.makedirs(TEMP_STORAGE, exist_ok=True)


@router.post("/api/upload")
async def upload_invoice(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not file.content_type or not file.content_type.startswith(("image/", "application/pdf")):
        raise HTTPException(status_code=400, detail="Only images and PDFs allowed")

    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    job_id, ocr_text = extract_text(file_bytes, file.filename)

    parsed = parse_ocr_text(ocr_text)

    contractor_name = parsed.get("contractor") or "unknown_contractor"
    purchased_from = parsed.get("source") or "unknown_source"

    import re
    contractor_name = re.sub(r'[^\w\-_]', '_', contractor_name.strip())
    purchased_from = re.sub(r'[^\w\-_]', '_', purchased_from.strip())

    today_date = datetime.now().strftime("%Y%m%d")

    _, file_extension = os.path.splitext(file.filename)
    if not file_extension:
        file_extension = ".jpg"

    new_filename = f"{contractor_name}_{purchased_from}_{today_date}{file_extension}"

    new_temp_path = os.path.join(TEMP_STORAGE, new_filename)
    with open(new_temp_path, "wb") as f:
        f.write(file_bytes)

    temp_filename = f"{job_id}_{file.filename}"
    temp_path = os.path.join(TEMP_STORAGE, temp_filename)
    with open(temp_path, "wb") as f:
        f.write(file_bytes)

    contractors = db.query(Contractor).all()
    sources = db.query(Source).all()

    return {
        "job_id": job_id,
        "filename": new_filename,
        "original_filename": file.filename,
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
    temp_files = [f for f in os.listdir(TEMP_STORAGE) if f.startswith(job_id + "_")]
    if not temp_files:
        raise HTTPException(status_code=404, detail="Job not found")

    temp_filename = temp_files[0]
    temp_path = os.path.join(TEMP_STORAGE, temp_filename)
    original_filename = temp_filename[len(job_id) + 1:]

    with open(temp_path, "rb") as f:
        file_bytes = f.read()

    _, ocr_text = extract_text(file_bytes, original_filename)
    parsed = parse_ocr_text(ocr_text)

    contractors = db.query(Contractor).all()
    sources = db.query(Source).all()

    return templates.TemplateResponse("review.html", {
        "request": request,
        "job_id": job_id,
        "filename": original_filename,
        "ocr_text": ocr_text,
        "parsed": parsed,
        "contractors": contractors,
        "sources": sources,
        "user": current_user
    })


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

    temp_files = [f for f in os.listdir(TEMP_STORAGE) if f.startswith(job_id + "_")]
    if not temp_files:
        raise HTTPException(status_code=404, detail="Job not found")

    temp_filename = temp_files[0]
    temp_path = os.path.join(TEMP_STORAGE, temp_filename)

    contractor = db.query(Contractor).filter(Contractor.id == contractor_id).first()
    source = db.query(Source).filter(Source.id == source_id).first()
    if not contractor or not source:
        raise HTTPException(status_code=400, detail="Invalid contractor or source")

    from app.schemas import ConfirmRequest
    confirm_data = ConfirmRequest(
        job_id=job_id,
        contractor_id=contractor_id,
        source_id=source_id,
        date=invoice_date,
        amount=str(invoice_amount)
    )

    with open(temp_path, "rb") as f:
        file_bytes = f.read()
    _, ocr_text = extract_text(file_bytes, filename)
    ocr_json = json.dumps({"text": ocr_text, "parsed": parse_ocr_text(ocr_text)})

    invoice = process_confirm(
        db=db,
        user_id=current_user.id,
        temp_file_path=temp_path,
        original_filename=filename,
        confirm_data=confirm_data,
        contractor_short=contractor.short_code,
        source_short=source.short_code,
        ocr_json=ocr_json
    )

    for f in os.listdir(TEMP_STORAGE):
        if f.startswith(job_id + "_"):
            try:
                os.remove(os.path.join(TEMP_STORAGE, f))
            except:
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
            file_path=inv.file_path,
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
            file_path=inv.file_path,
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
                "file_path": inv.file_path,
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