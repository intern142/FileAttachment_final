import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse

from .database import init_db, engine
from .models import Base, Contractor, Source, User
from .api import auth, routes
from .core.config import get_settings
from .api.auth import get_current_user, get_current_user_optional
from sqlalchemy.orm import Session

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = Session(bind=engine)
    try:
        if db.query(Contractor).count() == 0:
            contractors = [
                Contractor(name="ABC Constructions", short_code="ABC"),
                Contractor(name="XYZ Builders", short_code="XYZ"),
                Contractor(name="PQR Infra", short_code="PQR"),
            ]
            db.add_all(contractors)
        if db.query(Source).count() == 0:
            sources = [
                Source(name="WhatsApp", short_code="WA"),
                Source(name="Email", short_code="EM"),
                Source(name="Portal", short_code="PT"),
            ]
            db.add_all(sources)
        db.commit()
    finally:
        db.close()
    yield


app = FastAPI(title="Invoice Manager", lifespan=lifespan)

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