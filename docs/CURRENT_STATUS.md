# Current Status

## What Was Completed
- **JPG Conversion on Upload**: Images (PNG, etc.) now automatically converted to JPG before saving (commit 75bdace, 3e52059)
- **File Visibility in App**: Uploaded files now display correctly in the web UI with "Upload another" button (commit 3e52059)
- **Tesseract Auto-Detection**: Windows local dev now auto-detects Tesseract OCR path (commit 8c644d4)
- **Auto-Extraction**: Contractor and purchased-from fields extracted on upload, saved as `CONTRACTOR--PURCHASED_FROM--DATE` filename (commit 5acddb8)
- **Auth Fixes**: Cookie-based auth for page navigation, redirects for anonymous users, bcrypt compatibility (commits 3804aca, b899e81, 24b32fd, 58dc9ea)
- **Upload Flow Fixes**: Confirm redirect to `/` (upload page), review form posts to `/confirm`, HTMX 303 redirects (commits 85c8412, 3b96373, 10e3041, 565808f)

## What Remains
### General Remaining Items
- Database migrations for production (currently using SQLite dev DB)
- Production deployment config (Docker, environment variables)
- Comprehensive test coverage (unit + integration)
- Error handling for OCR failures / invalid uploads
- Rate limiting / upload size limits
- Multi-user isolation testing

## Files Changed (Recent)
- `invoice-web/frontend/templates/upload.html` - Added "Upload another" button, hide/show upload card after success
- `invoice-web/backend/app/api/routes.py` - Added PIL-based JPG conversion on upload
- `invoice-web/backend/app/__init__.py` - Added missing package init
- `invoice-web/backend/app/database/__init__.py` - Added missing package init

## Bugs Discovered
- None critical in recent commits. Previous bcrypt 4.0.1 compatibility issue fixed (commit 24b32fd)
- Server logs show clean startup (server_err.log: only INFO messages)

## Decisions Made
- Use PIL/Pillow for image conversion (JPG output, quality=95, RGB conversion for RGBA/P/LA modes)
- Store extracted files in organized directory: `storage/{user_id}/Q{quarter}/{month}/Week_{week}/`
- Filename format: `CONTRACTOR--PURCHASED_FROM--DATE.jpg` (spaces preserved, special chars handled)
- Auth via HttpOnly cookie + Authorization header support for HTMX navigation
- Redirect to `/` (upload page) after confirm instead of invoices list

## Next Recommended Steps
1. Add pytest test suite (backend API + frontend HTMX interactions)
2. Create Dockerfile + docker-compose for production
3. Add environment-based config (SECRET_KEY, DB_URL, TESSERACT_PATH)
4. Implement upload validation (file type, size limit, rate limiting)
5. Add database migration tool (Alembic) for schema changes
6. Consider async OCR processing for large files

## Member B Tasks (from file_copy)
### What Remains (Member B Scope)
- `organize.py` - generate_path(), move_file(), save_db()
- POST /api/confirm - parse date, generate path, move to storage, save Invoice row
- GET /invoices - list with filters (date, contractor, source), pagination
- Download endpoints
- AuditLog integration in confirm + list routes
- list.html template
- Wire review.html confirm button (already exists, posts to /api/confirm)

### Files Changed (Member A)
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

### Bugs Discovered & Fixed (Member A)
1. **psycopg2-binary build failure** - Missing libpq-dev + gcc in Dockerfile → added
2. **pydantic_settings missing** - Added to requirements.txt
3. **email-validator missing** - Required for EmailStr, added to requirements.txt
4. **Syntax error in main.py** - Missing colon after `try:` → fixed
5. **Template paths** - Frontend not copied to container → fixed Dockerfile COPY paths
6. **Build context** - Dockerfile in backend/ but context is root → updated docker-compose.yml build config
7. **passlib + bcrypt incompatibility** - `AttributeError: bcrypt has no __about__` and `ValueError: password cannot be longer than 72 bytes` caused `/auth/register` → 500. Fixed by pinning `passlib[bcrypt]==1.7.4` and `bcrypt==4.0.1` in requirements.txt; also installed pinned versions inside the running container and restarted (image pip layer was cached).
8. **Templates missing in container** - `RuntimeError: File at path frontend/templates/upload.html does not exist` on `/` and `/login` → 500, because `./backend:/app` bind-mount shadowed the image's `/app/frontend`. Fixed by adding `./frontend:/app/frontend` volume to docker-compose.yml.
9. **401 on protected routes despite valid token** - `get_current_user` parsed the JWT payload (which carries `sub`) into `TokenData(user_id=...)`, always yielding `None` → 401 "Could not validate credentials". Fixed in `auth.py` by reading `sub` directly and converting to int.
10. **bcrypt 5.0.0 still active in running container** - Despite requirements.txt pinning, the image pip layer was cached. Fixed by `pip install --force-reinstall bcrypt==4.0.1 passlib==1.7.4` inside the container + restart; verified `bcrypt 4.0.1` / `passlib 1.7.4`.

### E2E Verification (Member A flow, done locally)
- `POST /auth/register` (JSON) → 200, returns `access_token`
- `POST /auth/login` (form-urlencoded) → 200, returns `access_token`
- `POST /api/upload` (Bearer + multipart file `storage/temp/test_invoice.png`) → 200, `job_id` + OCR text + parsed contractor/source/date/amount + contractor/source dropdown options
- `GET /review/{job_id}` (Bearer) → 200, full review page with `/temp/{job_id}_{filename}` image preview and form pre-filled from OCR
- `GET /` → 200

Note: OCR `amount` prefill comes back as raw line `Amount: 1250.00 USD` (not stripped to number) - cosmetic, backend.net parsing is enough to display; confirm endpoint can clean it.

### Decisions Made (Member A)
- Sync OCR (no queue) - simpler for 3-hour scope
- Server-rendered HTMX/Jinja2 - no frontend build step
- Local ./storage bind-mounted in Docker
- JWT HS256 with 30-min expiry
- Contractors/Sources seeded on startup (3 each)
- Temp files in /storage/temp/ served via StaticFiles at /temp/

### Next Recommended Steps (Member B)
1. **Member B** pulls Member_A branch, copies 3 shared files (models.py, schemas.py, auth.py)
2. Member B implements:
   - `backend/app/services/organize.py`
   - POST /api/confirm in routes.py
   - GET /invoices in routes.py
   - AuditLog writes
   - list.html template
3. Test full flow: Upload → OCR → Review → Confirm → List/Download
4. Verify folder structure: /storage/{user}/{quarter}/{month}/Week_{n}/{contractor_short}-{source_short}-{YYYYMMDD}.ext