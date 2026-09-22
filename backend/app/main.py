from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import os

from app.database import engine, get_db
from app.models import Base, Contractor, Source
from app.api import auth, routes
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    
    db = next(get_db())
    try        if db.query(Contractor).count() == 0:
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

app.mount("/temp", StaticFiles(directory=os.path.join(settings.STORAGE_PATH, "temp")), name="temp")

app.include_router(auth.router)
app.include_router(routes.router)


@app.get("/")
async def root():
    return FileResponse("frontend/templates/upload.html")


@app.get("/upload")
async def upload_page():
    return FileResponse("frontend/templates/upload.html")


@app.get("/login")
async def login_page():
    return FileResponse("frontend/templates/login.html")


@app.get("/register")
async def register_page():
    return FileResponse("frontend/templates/register.html")