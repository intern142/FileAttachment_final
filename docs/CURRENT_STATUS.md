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

## What Remains (Member B Scope)

- `organize.py` - generate_path(), move_file(), save_db()
- POST /api/confirm - parse date, generate path, move to storage, save Invoice row
- GET /invoices - list with filters (date, contractor, source), pagination
- Download endpoints
- AuditLog integration in confirm + list routes
- list.html template
- Wire review.html confirm button (already exists, posts to /api/confirm)

## Files Changed (Member A)

```
docker-compose.yml
backend/Dockerfile
backend/requirements.txt
backend/app/__init__.py
backend/app/core/config.py
backend/app/core/security.py
backend/app/core/__init__.py
backend/app/models.py
backend/app/schemas.py
backend/app/database.py
backend/app/main.py
backend/app/api/__init__.py
backend/app/api/auth.py
backend/app/api/routes.py
backend/app/services/__init__.py
backend/app/services/ocr.py
frontend/templates/base.html
frontend/templates/upload.html
frontend/templates/review.html
frontend/templates/login.html
frontend/templates/register.html
```

## Bugs Discovered & Fixed

1. **psycopg2-binary build failure** - Missing libpq-dev + gcc in Dockerfile → added
2. **pydantic_settings missing** - Added to requirements.txt
3. **email-validator missing** - Required for EmailStr, added to requirements.txt
4. **Syntax error in main.py** - Missing colon after `try:` → fixed
5. **Template paths** - Frontend not copied to container → fixed Dockerfile COPY paths
6. **Build context** - Dockerfile in backend/ but context is root → updated docker-compose.yml build config
7. **passlib + bcrypt incompatibility** - `AttributeError: bcrypt has no __about__` and `ValueError: password cannot be longer than 72 bytes` caused `/auth/register` → 500. Fixed by pinning `passlib[bcrypt]==1.7.4` and `bcrypt==4.0.1` in requirements.txt, then rebuilding with `--no-cache`.

## Decisions Made

- Sync OCR (no queue) - simpler for 3-hour scope
- Server-rendered HTMX/Jinja2 - no frontend build step
- Local ./storage bind-mounted in Docker
- JWT HS256 with 30-min expiry
- Contractors/Sources seeded on startup (3 each)
- Temp files in /storage/temp/ served via StaticFiles at /temp/

## Next Recommended Steps

1. **Member B** pulls Member_A branch, copies 3 shared files (models.py, schemas.py, auth.py)
2. Member B implements:
   - `backend/app/services/organize.py`
   - POST /api/confirm in routes.py
   - GET /invoices in routes.py
   - AuditLog writes
   - list.html template
3. Test full flow: Upload → OCR → Review → Confirm → List/Download
4. Verify folder structure: /storage/{user}/{quarter}/{month}/Week_{n}/{contractor_short}-{source_short}-{YYYYMMDD}.ext
