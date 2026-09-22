import os
import uuid
import shutil
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.api.auth import get_current_user
from app.models import User, Contractor, Source, Invoice, InvoiceStatus
from app.schemas import OCRResult, ContractorResponse, SourceResponse
from app.services.ocr import extract_text, parse_ocr_text
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
    
    temp_filename = f"{job_id}_{file.filename}"
    temp_path = os.path.join(TEMP_STORAGE, temp_filename)
    with open(temp_path, "wb") as f:
        f.write(file_bytes)
    
    parsed = parse_ocr_text(ocr_text)
    
    contractors = db.query(Contractor).all()
    sources = db.query(Source).all()
    
    return {
        "job_id": job_id,
        "filename": file.filename,
        "ocr_text": ocr_text,
        "parsed": parsed,
        "contractors": [{"id": c.id, "name": c.name, "short_code": c.short_code} for c in contractors],
        "sources": [{"id": s.id, "name": s.name, "short_code": s.short_code} for s in sources]
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
    original_filename = temp_filename[len(job_id) + 1:]
    temp_path = os.path.join(TEMP_STORAGE, temp_filename)
    
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