import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .database import engine, get_db
from .models import Base, Contractor, Source, User
from .api import auth, routes
from .core.config import settings
from .api.auth import get_current_user_optional
from sqlalchemy.orm import Session


BASE_DIR = os.getcwd()


class CSPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "connect-src 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


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
    yield


app = FastAPI(title="Invoice Manager", lifespan=lifespan)

app.add_middleware(CSPMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(routes.router)

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "frontend", "templates"))

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "frontend", "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request, current_user: User = Depends(get_current_user_optional)):
    if not current_user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("upload.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.get("/invoices", response_class=HTMLResponse)
async def invoices_page(request: Request):
    return RedirectResponse(url="/invoices/page")