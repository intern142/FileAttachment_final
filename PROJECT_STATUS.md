# Project Status - Invoice Manager

**Last Updated:** 2026-10-05
**Branch:** `main` (all 3 PRs merged)
**Latest Commit:** `623ae79` (PR 3 restructure)

---

## ✅ Completed Tasks (Full Project - All Phases)

### Phase 1: Organize Service Fixes (PR 1 - `pr1-organize-fixes`)
- [x] Fixed absolute imports in `invoice-web/backend/app/services/organize.py`
- [x] Corrected `InvoiceStatus.CONFIRMED` enum usage (uppercase)
- [x] Fixed `settings.STORAGE_PATH` attribute access
- [x] Added missing `except` block in `review_invoice()` for proper error handling

### Phase 2: Security Hardening (PR 2 - `pr2-security`)
- [x] Rate limiting on `/auth/register` (3/hr), `/auth/login` (5/5min), `/api/upload` (10/min)
- [x] Token blocklist for logout (`/auth/logout` endpoint)
- [x] MIME validation via `python-magic` (magic bytes)
- [x] Path traversal protection (`validate_file_path()`)
- [x] OCR text sanitization (`sanitize_ocr_text()`)
- [x] Authenticated temp file endpoint: `/api/temp-file/{job_id}/{filename}`
- [x] CSP middleware with security headers
- [x] Auth form error handling (429, 4xx display)

### Phase 3: Backend Restructure + PostgreSQL (PR 3 - `pr3-restructure`)
- [x] New `/backend` directory with complete service layer separation
- [x] **Alembic migrations** (`alembic.ini`, `env.py`, initial migration)
- [x] **PostgreSQL-ready** (`psycopg2`, `DATABASE_URL` configurable)
- [x] **Models**: User, Contractor, Source, Invoice, AuditLog (with indexes)
- [x] **Schemas**: Complete Pydantic models with `InvoiceFilters`, `InvoiceListItem`
- [x] **Services**:
  - `organize.py` - Structured storage paths, file moves, audit logging
  - `ocr.py` - Text extraction + basic parsing + XSS sanitization
  - `utils/security.py` - Path helpers, text sanitization
- [x] **Auth API**: JSON body register, OAuth2 form login, token blocklist, rate limits
- [x] **API Routes**: New paginated endpoints (`/invoices`, `/invoices/table`, `/api/invoices`, `/invoices/stats`)
- [x] **Main App**: CSP middleware, lifespan with DB init + seeding
- [x] **Frontend**: New `list.html`, `partials/invoice_table.html`, `confirm_success.html`
- [x] **Docker**: Updated `docker-compose.yml` for PostgreSQL + new structure
- [x] **Config**: `.env.example` with required `SECRET_KEY`, rate limit settings

---

## 📁 File Tree (main branch - restructured)

```
FileAttachment_final/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── PROJECT_STATUS.md
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   ├── README
│   │   └── versions/
│   │       └── 88f8dd99534b_initial_migration.py
│   └── app/
│       ├── __init__.py
│       ├── main.py
│       ├── models.py
│       ├── schemas.py
│       ├── database.py
│       ├── api/
│       │   ├── __init__.py
│       │   ├── auth.py
│       │   └── routes.py
│       ├── services/
│       │   ├── __init__.py
│       │   ├── ocr.py
│       │   └── organize.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   └── security.py
│       └── utils/
│           ├── __init__.py
│           └── security.py
├── frontend/
│   └── templates/
│       ├── base.html
│       ├── upload.html
│       ├── review.html
│       ├── list.html
│       ├── login.html
│       ├── register.html
│       ├── confirm_success.html
│       └── partials/
│           └── invoice_table.html
└── storage/ (created at runtime)
```

---

## 🚀 How to Run (Local Development)

```bash
# 1. Clone
git clone https://github.com/intern142/FileAttachment_final.git
cd FileAttachment_final

# 2. Create .env in backend/
cd backend
echo "DATABASE_URL=sqlite:///./invoice_manager.db" > .env
echo "STORAGE_PATH=./storage" >> .env
echo "SECRET_KEY=dev-secret-change-me" >> .env

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 5. Open browser
# http://localhost:8000
```

### With Docker (Production/PostgreSQL)

```bash
# 1. Copy .env.example and set SECRET_KEY
cp .env.example .env
# Edit .env with strong SECRET_KEY

# 2. Start services
docker-compose up --build

# 3. Run migrations (first time)
docker-compose exec backend alembic upgrade head

# 4. Open browser
# http://localhost:8000
```

---

## 🔄 User Flow

1. **Register** → `/register` → auto-login → upload page
2. **Login** → `/login` → upload page
3. **Upload** → Drop image/PDF → OCR runs → redirects to `/review/{job_id}`
4. **Review** → Edit contractor/source/date/amount → **Confirm & Save**
5. **List** → `/invoices` → Filter, paginate, download, copy file

---

## 🔑 Key Technical Decisions

| Area | Decision |
|------|----------|
| **Database** | SQLite for local dev, PostgreSQL for production (via `DATABASE_URL`) |
| **Migrations** | Alembic with autogenerate support |
| **Auth** | JWT (HS256), 30-min expiry, token blocklist on logout |
| **Storage** | Structured: `/storage/{user_id}/Q{N}/{month}/Week_{NN}/{contractor}-{source}-{date}.ext` |
| **OCR** | pytesseract + pdf2image + PIL, basic keyword parsing |
| **Security** | CSP, rate limits, MIME validation, path traversal protection, XSS sanitization |
| **Frontend** | Tailwind CSS (CDN), HTMX 1.9.10, Jinja2 templates |

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
- No automated tests, CI/CD pipeline
- No OAuth, S3 storage, Celery workers, WebSockets
- Temp files in `/tmp/invoice_uploads` (ephemeral, per-job)
- Single-user demo (no multi-org isolation)

---

## 📝 Next Steps

1. ✅ **Phase 1**: Organize service fixes (merged)
2. ✅ **Phase 2**: Security hardening (merged)
3. ✅ **Phase 3**: Backend restructure + PostgreSQL + Alembic (merged)
4. **Future**: Add tests, CI/CD, improve OCR, deploy to staging

---

## 📊 PR Summary

| PR | Branch | Focus | Files | Lines |
|----|--------|-------|-------|-------|
| #1 | `pr1-organize-fixes` | Organize service fixes | 2 | +28/-27 |
| #2 | `pr2-security` | Security hardening | 8 | +505/-66 |
| #3 | `pr3-restructure` | Full backend restructure | 38 | +1273/-84 |

---

**Status:** ✅ All 3 PRs merged to `main`. Server runs locally with SQLite. Ready for PostgreSQL deployment via Docker.
---

## 2026-10-05 (Evening) - Upload Persistence, Review Flow, Invoice Actions

Branch: fix-review-preview (not yet merged to main)

### Upload result UI (commit 54c8d71)
- [x] Upload response no longer dumps raw JSON (contractors/sources/message)
- [x] Shows renamed invoice filename with 3 buttons: Review, Rename (modal), Delete
- [x] New endpoints: POST /api/upload/{job_id}/rename, DELETE /api/upload/{job_id}
- [x] Fixed htmx handler bug: checked evt.target.id instead of evt.detail.elt.id; form now uses hx-swap="none"

### Auth fix for review page (commit bd778c4)
- [x] get_current_user now falls back to access_token cookie (401 on /review fixed)
- [x] oauth2_scheme uses auto_error=False

### Invoice persistence + actions (commit 85780dd)
- [x] Root cause of disappearing invoices: upload never created an invoices DB row (only /api/confirm did). Upload now creates a PENDING invoice row immediately (contractor/source get-or-create, parsed date/amount, stored renamed file path)
- [x] /api/confirm updates the pending row instead of inserting a duplicate (process_confirm fallback retained)
- [x] Rename persists: upload rename endpoint syncs DB row (file_path/date/contractor/source); list rename renames stored file
- [x] Delete permanently removes stored file + DB row
- [x] New POST /invoices/{id}/confirm (pending -> confirmed)
- [x] New POST /invoices/{id}/review-confirm: editable contractor/source/date/amount, renames stored file to structured folder, sets CONFIRMED
- [x] Per-row actions: Review | Download | Confirm | Rename | Delete (flex row, no overlap)
- [x] Review modal moved out of htmx-swapped partial into list.html so buttons stay responsive; preview via /api/invoice-file img/iframe
- [x] Cookie fallback when localStorage token is expired/stale

### Verified
- [x] Upload -> /invoices shows invoice; survives refresh, logout/login, container restart (Postgres 16 + /storage volume)
- [x] Review/Rename/Delete/Confirm persist after refresh
