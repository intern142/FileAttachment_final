# Current Project Status

## What Was Completed (Member A)

**Infrastructure & Core**
- Docker Compose setup (PostgreSQL + Backend)
- Backend Dockerfile with Tesseract, Poppler, build tools
- Requirements: FastAPI, SQLAlchemy 2.0, Pydantic, JWT auth, OCR deps

**Backend Core**
- `config.py` - Settings from env (DATABASE_URL, STORAGE_PATH, SECRET_KEY)
- `security.py` - JWT HS256, bcrypt password hashing, token create/verify
- `models.py` - User, Contractor, Source, Invoice, AuditLog with indexes
- `schemas.py` - Pydantic models for all endpoints
- `database.py` - SQLAlchemy session dependency
- `main.py` - FastAPI with lifespan seeding contractors/sources

**Auth API**
- `auth.py` - POST /auth/register, POST /auth/login, get_current_user dependency

**OCR Service**
- `ocr.py` - extract_text() for JPG/PNG/PDF via pytesseract + pdf2image
- parse_ocr_text() - basic field extraction (contractor, source, date, amount)

**Upload Flow**
- POST /api/upload - saves temp file, runs OCR sync, returns job_id + parsed data
- GET /review/{job_id} - renders review template with image preview + editable fields

**Frontend Templates**
- base.html - shared layout with HTMX + Tailwind CDN
- upload.html - drag/drop dropzone, HTMX post to /api/upload
- review.html - image preview + editable form (contractor, source, date, amount) posting to /api/confirm
- login.html, register.html - HTMX auth forms

## What Was Completed (Member B - feature1 branch)

**Enhanced Upload Flow**
- Modified POST /api/upload to:
  - Extract contractor name and purchased from (source) from OCR
  - Use today's actual date instead of extracted date from document
  - Generate smart filename format: {contractor_name}_{purchased_from}_{YYYYMMDD}.{extension}
  - Save file with new name immediately in temp storage
  - Return minimal JSON response WITHOUT raw OCR text or parsed data (hides extraction from user)
  - Maintain compatibility with review endpoint for workflow continuity

**Verification**
- Tested feature through API calls with authentication
- Confirmed raw OCR data is not exposed in API responses
- Verified filename generation works correctly with real invoice files
- Application runs successfully on http://localhost:8001 using docker-compose-test.yml

## What Was Completed (This Session - Main Branch)

**Missing Endpoints Implemented**
- Created `backend/app/services/organize.py` - Path generation, file move, DB save, audit logging
  - Folder structure: `/storage/{user}/{quarter}/{month}/Week_{n}/{contractor_short}-{source_short}-{YYYYMMDD}.ext`
- Implemented all missing API endpoints in `backend/app/api/routes.py`:
  - `POST /api/confirm` - Parse date, call organize service, save Invoice, audit log
  - `GET /invoices` (HTML page) - Full page with filters, pagination
  - `GET /invoices/table` (HTML partial) - HTMX partial for filtering/pagination
  - `GET /api/invoices` (JSON) - API endpoint with filters/pagination
  - `GET /invoices/stats` - Dashboard stats
  - `GET /contractors`, `GET /sources` - Dropdown data
  - `GET /invoices/{id}/download` - File download
  - `GET /api/invoice-file/{id}` - For copy-to-clipboard feature

**Docker Fixes**
- Fixed `invoice-web/backend/app/main.py` - Removed `/static` mount causing startup error
- Fixed `invoice-web/backend/app/api/auth.py` - Added `get_current_user_optional` function

**Frontend Templates Already Existed**
- list.html - Filter form + HTMX table partial
- partials/invoice_table.html - Reusable table with pagination

## What Remains

- Test full flow end-to-end: Upload → OCR → Review → Confirm → List/Download
- Verify folder structure: `/storage/{user}/{quarter}/{month}/Week_{n}/{contractor_short}-{source_short}-{YYYYMMDD}.ext`
- Docker build takes 5-10 minutes (installing tesseract, poppler, gcc, etc.)

## Files Changed (This Session)

```
backend/app/services/organize.py              # NEW
backend/app/api/routes.py                     # Added all missing endpoints
invoice-web/backend/app/main.py               # Fixed static mount issue
invoice-web/backend/app/api/auth.py           # Added get_current_user_optional
```

## Bugs Discovered & Fixed (This Session)

1. **Missing `organize.py` service** - Created from `invoice-web/backend/app/services/organize.py` with adjusted imports
2. **Missing API endpoints** - Implemented all confirm, list, stats, download endpoints
3. **Docker startup error** - `/static` mount referenced non-existent `frontend/static` directory
4. **Missing `get_current_user_optional`** - Added to `invoice-web/backend/app/api/auth.py` for root route compatibility
5. **Docker layer caching** - Image rebuild required `--no-cache` to pick up code changes

## Decisions Made

- Sync OCR (no queue) - simpler for scope
- Server-rendered HTMX/Jinja2 - no frontend build step
- Local ./storage bind-mounted in Docker
- JWT HS256 with 30-min expiry
- Contractors/Sources seeded on startup (3 each)
- Temp files in /storage/temp/ served via StaticFiles at /temp/
- **Member B decision**: Hide raw OCR data from users while extracting needed fields for smart filenames
- **Member B decision**: Use today's actual date instead of extracted date for filename consistency
- **Member B decision**: Smart filename format: {contractor}_{purchasedfrom}_{YYYYMMDD}.{extension}
- **This session**: Use existing `invoice-web/backend/app/services/organize.py` as reference for file organization logic

## Next Recommended Steps

1. **Wait for Docker build to complete** (5-10 min - installing system packages)
2. **Test full flow**: Register → Login → Upload → OCR → Review → Confirm → List/Download
3. **Verify folder structure**: `/storage/{user}/{quarter}/{month}/Week_{n}/{contractor_short}-{source_short}-{YYYYMMDD}.ext`
4. **Test download and copy-to-clipboard** functionality
5. **Merge feature1 branch into main** after verification