# Project Status - Invoice Manager

**Last Updated:** 2026-09-28
**Branch:** `feature1`
**Latest Commit:** (check `git log --oneline -1`)

---

## ✅ Completed Tasks

### Infrastructure
- [x] `docker-compose.yml` - PostgreSQL 16 + Backend services (context: root, dockerfile: ./backend/Dockerfile)
- [x] `backend/Dockerfile` - Python 3.11-slim with Tesseract + Poppler + libpq + gcc
- [x] `backend/requirements.txt` - All dependencies pinned (bcrypt 4.0.1, passlib 1.7.4)

### Core Backend
- [x] `backend/app/core/config.py` - Pydantic Settings (env-based)
- [x] `backend/app/core/security.py` - JWT (HS256), bcrypt password hashing
- [x] `backend/app/database.py` - SQLAlchemy 2.0 engine, session, init_db

### Models & Schemas
- [x] `backend/app/models.py` - User, Contractor, Source, Invoice, AuditLog
- [x] `backend/app/schemas.py` - Pydantic models for all API contracts

### Auth API
- [x] `backend/app/api/auth.py` - `/auth/register` (form-data), `/auth/login` (form-data), `get_current_user` dependency
- [x] Register accepts `application/x-www-form-urlencoded` (HTMX compatible)
- [x] Login uses OAuth2PasswordRequestForm (form-data)

### OCR Service
- [x] `backend/app/services/ocr.py` - `extract_text()` for JPG/PNG/PDF via pytesseract + pdf2image
- [x] `parse_ocr_text()` - basic field extraction (contractor, source, date, amount)

### Upload Flow (Modified by Member B)
- [x] `POST /api/upload` - Save temp file, run OCR sync, return job_id + dropdown data
  - **Member B changes**: Hides raw OCR text/parsed data from response, generates smart filename `{contractor}_{source}_{YYYYMMDD}.ext`, uses today's date instead of extracted date
- [x] `GET /review/{job_id}` - Render review page with image preview + editable fields (contractor, source, date, amount dropdowns)

### Frontend Templates
- [x] `frontend/templates/base.html` - Bootstrap 5 + HTMX + auth header injection
- [x] `frontend/templates/upload.html` - Dropzone, file preview, HTMX upload → redirect to review
- [x] `frontend/templates/review.html` - Image preview, editable fields, HTMX confirm → redirect to list
- [x] `frontend/templates/list.html` - Filter form + HTMX table partial
- [x] `frontend/templates/partials/invoice_table.html` - Reusable table with pagination
- [x] `frontend/templates/login.html` - HTMX form, stores JWT in localStorage, redirects to `/`
- [x] `frontend/templates/register.html` - HTMX form, stores JWT in localStorage, redirects to `/`

### Main App Setup
- [x] `backend/app/main.py` - FastAPI + lifespan (DB init + seed contractors/sources)
- [x] Static files mounted at `/temp` for uploaded file preview
- [x] Route protection: `/` (upload) requires valid JWT via `Depends(get_current_user_optional)`
- [x] `/login` and `/register` pages accessible without auth

---

## ❌ INCOMPLETE / MISSING (Critical Path)

### API Endpoints - NOT IMPLEMENTED
| Endpoint | Status | Notes |
|----------|--------|-------|
| `POST /api/confirm` | ❌ Missing | Parse date, call organize service, save Invoice, audit log |
| `GET /invoices` (JSON) | ❌ Missing | List with filters, pagination |
| `GET /invoices/page` (HTML) | ❌ Missing | Full page render (uses `list.html`) |
| `GET /invoices/table` (HTML partial) | ❌ Missing | HTMX partial for filtering/pagination |
| `GET /invoices/stats` | ❌ Missing | Dashboard stats |
| `GET /contractors` | ❌ Missing | Dropdown data |
| `GET /sources` | ❌ Missing | Dropdown data |
| `GET /invoices/{id}/download` | ❌ Missing | File download |
| `GET /api/invoice-file/{id}` | ❌ Missing | Referenced in invoice_table.html for download/copy |

### Services - MISSING
- [ ] `backend/app/services/organize.py` - **NOT PRESENT** (exists in `invoice-web/backend/app/services/organize.py` but not in main backend)
  - Path generation: `/storage/{user}/{quarter}/{month}/Week_{n}/{contractor_short}-{source_short}-{YYYYMMDD}.ext`
  - File move, DB save, audit logging

### AuditLog Integration
- [ ] AuditLog entries on confirm, download, etc.

---

## 📁 Current File Tree (main branch - actual)

```
invoice-web/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── models.py
│       ├── schemas.py
│       ├── database.py
│       ├── api/
│       │   ├── auth.py       ✅ Complete
│       │   └── routes.py     ⚠️ Partial (upload + review only)
│       ├── services/
│       │   ├── __init__.py
│       │   └── ocr.py        ✅ Complete
│       │   # organize.py      ❌ MISSING
│       └── core/
│           ├── config.py     ✅ Complete
│           └── security.py   ✅ Complete
├── frontend/
│   └── templates/
│       ├── base.html         ✅ Complete
│       ├── upload.html       ✅ Complete
│       ├── review.html       ✅ Complete
│       ├── list.html         ✅ Complete (but no backend endpoints)
│       ├── login.html        ✅ Complete
│       ├── register.html     ✅ Complete
│       └── partials/
│           └── invoice_table.html  ✅ Complete (but no backend data)
└── storage/ (created at runtime)
```

---

## 🚀 How to Run

### Option 1: Docker (recommended)
```bash
# 1. Clone
git clone https://github.com/intern142/FileAttachment_final.git
cd FileAttachment_final

# 2. Start services
cd invoice-web
docker-compose up --build

# 3. Open browser
# http://localhost:8000 (or http://<your-lan-ip>:8000 for LAN access)
```

### Option 2: Local Python (SQLite)
```bash
cd invoice-web/backend
pip install -r requirements.txt
# Create .env with: DATABASE_URL=sqlite:///./invoice_manager.db
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# http://localhost:8000
```

### Flow Test (Current State)
1. **Register** → `/register` → auto-login → upload page ✅
2. **Login** → `/login` → upload page ✅
3. **Upload** → Drop image/PDF → OCR runs → redirects to `/review/{job_id}` ✅
4. **Review** → Edit contractor/source/date/amount → **Confirm** → **❌ 404/500 (endpoint missing)**
5. **List** → `/invoices` → **❌ 404 (endpoint missing)**

---

## 🔑 Key Fixes Applied

| Issue | Fix |
|-------|-----|
| bcrypt 4.2.1 `__about__` error | Downgraded to `bcrypt==4.0.1` |
| passlib 1.7.0 72-byte limit | Upgraded to `passlib==1.7.4` |
| Register endpoint JSON-only | Changed to accept `Form(...)` for HTMX |
| Frontend JS response parsing | Added `JSON.parse()` fallback for HTMX `xhr.response` string |
| Template path resolution | Fixed `Jinja2Templates(directory="../frontend/templates")` |
| Config/Security refactor | Changed from `get_settings()` to `settings = Settings()` with uppercase attrs |
| Database Base import | Models now import `Base` from `database.py` (single source of truth) |
| Form-data register | `/auth/register` accepts `application/x-www-form-urlencoded` |
| Route protection | `/` now requires JWT via `Depends(get_current_user_optional)` |
| Login/Register pages | Added `/login` and `/register` templates with HTMX |
| Docker static files | Fixed volume mount (added `./frontend:/app/frontend`) |
| Static file paths | Used absolute paths via `BASE_DIR` in main.py |
| psycopg2 build | Added `libpq-dev`, `gcc`, `build-essential` to Dockerfile |
| 401 on protected routes | Fixed `get_current_user` to read `sub` from JWT payload |

---

## ⚠️ Known Limitations

- OCR parsing is basic (keyword-based) — improve regex/ML later
- No tests, CI/CD, OAuth, S3, Celery, WebSockets
- Temp files in `/storage/temp/` (ephemeral)
- Single-user demo (no multi-org isolation)
- **Confirm & List endpoints not implemented**

---

## 📝 Next Steps (Priority Order)

1. **Copy `organize.py` from `invoice-web/backend/app/services/organize.py` to `backend/app/services/organize.py`**
2. **Implement `POST /api/confirm` in `routes.py`** - use organize service to:
   - Parse form data (job_id, contractor_id, source_id, date, amount)
   - Find temp file, move to permanent storage with organized path
   - Save Invoice row with CONFIRMED status
   - Create AuditLog entry
   - Redirect to `/invoices` page
3. **Implement `GET /invoices/page`** - render `list.html` with filters, contractors, sources
4. **Implement `GET /invoices/table`** - return `partials/invoice_table.html` for HTMX
5. **Implement `GET /invoices` (JSON)** - API endpoint with filters/pagination
6. **Implement `GET /invoices/stats`** - dashboard counts
7. **Implement `GET /contractors` and `GET /sources`** - dropdown data
8. **Implement `GET /invoices/{id}/download`** - file download
9. **Implement `GET /api/invoice-file/{id}`** - for copy-to-clipboard feature
10. Test full flow: Upload → OCR → Review → Confirm → List/Download
11. Verify folder structure: `/storage/{user}/{quarter}/{month}/Week_{n}/{contractor_short}-{source_short}-{YYYYMMDD}.ext`

---

## 📋 Implementation Notes for Next Session

### For `POST /api/confirm`:
- Input: `ConfirmRequest` schema (job_id, contractor_id, source_id, date, amount, filename)
- Find temp file in `TEMP_STORAGE` (either by job_id prefix or new_filename)
- Get contractor/source short_codes from DB
- Call `organize.process_confirm()` 
- Return redirect to `/invoices` or JSON success

### For `GET /invoices/page`:
- Query params: contractor_id, source_id, date_from, date_to, page, per_page
- Query DB with filters + pagination
- Pass `invoices`, `contractors`, `sources`, pagination data to `list.html`

### For `GET /invoices/table`:
- Same query as above but return `partials/invoice_table.html` partial

### For `organize.py`:
- Copy from `invoice-web/backend/app/services/organize.py` (already implemented)
- Adjust imports to match main backend structure (`from app.models import ...`)

---

**Status:** ✅ **Register + Login + Upload + Review working.** Need to implement Confirm + List + Download endpoints and copy organize service.