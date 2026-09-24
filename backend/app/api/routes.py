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

    parsed = parse_ocr_text(ocr_text)

    # Extract contractor name and purchased from (source) from OCR
    contractor_name = parsed.get("contractor") or "unknown_contractor"
    purchased_from = parsed.get("source") or "unknown_source"

    # Clean the names for use in filename (remove/replace problematic characters)
    import re
    contractor_name = re.sub(r'[^\w\-_]', '_', contractor_name.strip())
    purchased_from = re.sub(r'[^\w\-_]', '_', purchased_from.strip())

    # Use today's date instead of extracted date
    today_date = datetime.now().strftime("%Y%m%d")

    # Get file extension
    _, file_extension = os.path.splitext(file.filename)
    if not file_extension:
        file_extension = ".jpg"  # default to jpg if no extension

    # Create new filename: contractor_purchasedfrom_todaydate.extension
    new_filename = f"{contractor_name}_{purchased_from}_{today_date}{file_extension}"

    # Save file with new name immediately in temp storage
    new_temp_path = os.path.join(TEMP_STORAGE, new_filename)
    with open(new_temp_path, "wb") as f:
        f.write(file_bytes)

    # Also keep the original job_id temp file for compatibility with review flow?
    # Or we can modify the review flow to work with the new naming
    # For now, let's also create the job_id file to maintain compatibility
    temp_filename = f"{job_id}_{file.filename}"
    temp_path = os.path.join(TEMP_STORAGE, temp_filename)
    with open(temp_path, "wb") as f:
        f.write(file_bytes)

    # Return minimal info - do NOT show raw OCR data or parsed data to user
    contractors = db.query(Contractor).all()
    sources = db.query(Source).all()

    return {
        "job_id": job_id,
        "filename": new_filename,  # Return the new filename
        "original_filename": file.filename,
        "contractors": [{"id": c.id, "name": c.name, "short_code": c.short_code} for c in contractors],
        "sources": [{"id": s.id, "name": s.name, "short_code": s.short_code} for s in sources],
        # Note: NOT returning ocr_text or parsed data to hide raw extraction from user
        "message": "File uploaded successfully. Please review and confirm."
    }


@router.get("/review/{job_id}", response_class=HTMLResponse)
async def review_invoice(
    request: Request,
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Look for files that start with the job_id
    temp_files = [f for f in os.listdir(TEMP_STORAGE) if f.startswith(job_id + "_")]
    if not temp_files:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get the most recent file (should be our newly named file)
    temp_filename = temp_files[0]
    temp_path = os.path.join(TEMP_STORAGE, temp_filename)
    original_filename = temp_filename[len(job_id) + 1:]  # Remove job_id_ prefix

    with open(temp_path, "rb") as f:
        file_bytes = f.read()

    # Re-extract text for display in review (but we won't show raw data)
    _, ocr_text = extract_text(file_bytes, original_filename)
    parsed = parse_ocr_text(ocr_text)

    contractors = db.query(Contractor).all()
    sources = db.query(Source).all()

    return templates.TemplateResponse("review.html", {
        "request": request,
        "job_id": job_id,
        "filename": original_filename,
        "ocr_text": ocr_text,  # Still available for backend processing but not shown in UI
        "parsed": parsed,
        "contractors": contractors,
        "sources": sources,
        "user": current_user
    })