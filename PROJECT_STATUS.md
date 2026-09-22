# Project Status - Invoice Manager

**Last Updated:** 2026-09-22
**Branch:** `main` (merged from Member_B)
**Latest Commit:** `24b32fd`

---

## ✅ Completed Tasks (Full Project - Member A + Member B)

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

### Services
- [x] `backend/app/services/organize.py` - Path generation, file move, DB save, audit logging
  - Folder structure: `/storage/{user}/{quarter}/{month}/Week_{n}/{contractor_short}-{source_short}-{YYYYMMDD}.ext`

### API Routes
- [x] `backend/app/api/routes.py` - All endpoints:
  - `POST /api/upload` - Save temp file, run OCR sync, return job_id + extracted data
  - `GET /review/{job_id}` - Render review page with image + pre-filled fields
  - `POST /api/confirm` - Parse date, call organize service, save Invoice, audit log
  - `GET /invoices/page` - Full HTML page with filters (HTMX)
  - `GET /invoices/table` - Partial table for HTMX filtering/pagination
  - `GET /invoices` - JSON list (API)
  - `GET /invoices/stats` - Dashboard stats
  - `GET /contractors`, `GET /sources` - Dropdown data
  - `GET /invoices/{id}/download` - File download

### Main App
- [x] `backend/app/main.py` - FastAPI + lifespan (DB init + seed contractors/sources)
- [x] Route protection: `/` (upload) requires valid JWT via `Depends(get_current_user)`
- [x] `/login` and `/register` pages accessible without auth

### Frontend Templates
- [x] `frontend/templates/base.html` - Bootstrap 5 + HTMX + auth header injection
- [x] `frontend/templates/upload.html` - Dropzone, file preview, HTMX upload → redirect to review
- [x] `frontend/templates/review.html` - Image preview, editable fields, HTMX confirm → redirect to list
- [x] `frontend/templates/list.html` - Filter form + HTMX table partial
- [x] `frontend/templates/partials/invoice_table.html` - Reusable table with pagination
- [x] `frontend/templates/login.html` - HTMX form, stores JWT in localStorage, redirects to `/`
- [x] `frontend/templates/register.html` - HTMX form, stores JWT in localStorage, redirects to `/`

---

## 📁 File Tree (main branch)

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
│       │   ├── auth.py
│       │   └── routes.py
│       ├── services/
│       │   └── organize.py
│       └── core/
│           ├── config.py
│           └── security.py
├── frontend/
│   └── templates/
│       ├── base.html
│       ├── upload.html
│       ├── review.html
│       ├── list.html
│       ├── login.html
│       ├── register.html
│       └── partials/
│           └── invoice_table.html
└── storage/ (created at runtime)
```

---

## 🚀 How to Run

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

### Flow Test
1. **Register** → `/register` → auto-login → upload page
2. **Login** → `/login` → upload page
3. **Upload** → Drop image/PDF → OCR runs → redirects to `/review/{job_id}`
4. **Review** → Edit contractor/source/date/amount → **Confirm**
5. **List** → `/invoices` → Filter, paginate, download

---

## 🔑 Key Fixes Applied (Post Member_B)

| Issue | Fix |
|-------|-----|
| bcrypt 4.2.1 `__about__` error | Downgraded to `bcrypt==4.0.1` |
| passlib 1.7.0 72-byte limit | Upgraded to `passlib==1.7.4` |
| Register endpoint JSON-only | Changed to accept `Form(...)` for HTMX |
| Route protection | `/` now requires JWT via `Depends(get_current_user)` |
| Login/Register pages | Added `/login` and `/register` templates with HTMX |
| Docker static files | Fixed volume mount conflict (removed `./backend:/app`) |
| Static file paths | Used absolute paths via `BASE_DIR` in main.py |
| psycopg2 build | Added `libpq-dev`, `gcc`, `build-essential` to Dockerfile |

---

## 📡 LAN Access

```bash
# Find your LAN IP
ipconfig | findstr IPv4
# Share: http://<your-lan-ip>:8000

# Allow port 8000 in Windows Firewall (run as Admin):
New-NetFirewallRule -DisplayName "Invoice App" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

---

## ⚠️ Known Limitations (Out of Scope)

- OCR parsing is basic (keyword-based) — improve regex/ML later
- No tests, CI/CD, OAuth, S3, Celery, WebSockets
- Temp files in `/tmp/invoice_uploads` (ephemeral)
- Single-user demo (no multi-org isolation)

---

## 📝 Next Steps (if any)

1. Polish OCR extraction, add validation, improve UI
2. Deploy to staging (Render, Railway, Fly.io, etc.)

---

**Status:** ✅ All features complete, tested, and pushed to `main` (commit `24b32fd`).