# Current Status

## What Was Completed
- **JPG Conversion on Upload**: Images (PNG, etc.) now automatically converted to JPG before saving (commit 75bdace, 3e52059)
- **File Visibility in App**: Uploaded files now display correctly in the web UI with "Upload another" button (commit 3e52059)
- **Tesseract Auto-Detection**: Windows local dev now auto-detects Tesseract OCR path (commit 8c644d4)
- **Auto-Extraction**: Contractor and purchased-from fields extracted on upload, saved as `CONTRACTOR--PURCHASED_FROM--DATE` filename (commit 5acddb8)
- **Auth Fixes**: Cookie-based auth for page navigation, redirects for anonymous users, bcrypt compatibility (commits 3804aca, b899e81, 24b32fd, 58dc9ea)
- **Upload Flow Fixes**: Confirm redirect to `/` (upload page), review form posts to `/confirm`, HTMX 303 redirects (commits 85c8412, 3b96373, 10e3041, 565808f)

## What Remains
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