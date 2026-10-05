import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os
from pathlib import Path

from app.database import engine, get_db
from app.models import Base, Contractor, Source, User
from app.api import auth, routes
from app.api.auth import get_current_user_optional
from app.core.config import settings
from app.utils.security import sanitize_ocr_text, get_relative_file_path

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / "frontend" / "templates"

CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://unpkg.com; "
    "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
    "img-src 'self' data: https:; "
    "font-src 'self' https://cdn.tailwindcss.com; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    
    db = next(get_db())
    try:
        if db.query(Contractor).count() == 0:
            default_contractors = [
                Contractor(name="ABC Contractors", short_code="ABC"),
                Contractor(name="XYZ Builders", short_code="XYZ"),
                Contractor(name="PQR Engineering", short_code="PQR"),
            ]
            for c in default_contractors:
                db.add(c)
        
        if db.query(Source).count() == 0:
            default_sources = [
                Source(name="Materials", short_code="MAT"),
                Source(name="Labor", short_code="LAB"),
                Source(name="Equipment", short_code="EQP"),
                Source(name="Transport", short_code="TRN"),
            ]
            for s in default_sources:
                db.add(s)
        
        db.commit()
    finally:
        db.close()
    
    os.makedirs(settings.STORAGE_PATH, exist_ok=True)
    os.makedirs(os.path.join(settings.STORAGE_PATH, "temp"), exist_ok=True)
    
    yield


app = FastAPI(title="Invoice OCR", lifespan=lifespan)

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

app.include_router(auth.router)
app.include_router(routes.router)


# @app.middleware("http")
# async def add_security_headers(request: Request, call_next):
#     response: Response = await call_next(request)
#     response.headers["Content-Security-Policy"] = CSP_POLICY
#     response.headers["X-Content-Type-Options"] = "nosniff"
#     response.headers["X-Frame-Options"] = "DENY"
#     response.headers["X-XSS-Protection"] = "1; mode=block"
#     response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
#     return response


@app.get("/")
async def root(
    request: Request,
    current_user: User = Depends(get_current_user_optional),
):
    if current_user:
        return templates.TemplateResponse("upload.html", {"request": request, "user": current_user})
    return RedirectResponse(url="/login", status_code=302)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/upload")
async def upload_page(
    request: Request,
    current_user: User = Depends(get_current_user_optional),
):
    if current_user:
        return templates.TemplateResponse("upload.html", {"request": request, "user": current_user})
    return RedirectResponse(url="/login", status_code=302)


@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "user": None})


@app.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "user": None})