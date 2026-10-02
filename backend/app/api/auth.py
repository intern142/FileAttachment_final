from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import Optional
from collections import defaultdict
import time

from app.core.config import settings
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    decode_access_token,
)
from app.models import User
from app.schemas import UserCreate, UserLogin, Token
from app.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

_token_blocklist = set()

def is_token_blocked(token: str) -> bool:
    return token in _token_blocklist

def block_token(token: str) -> None:
    _token_blocklist.add(token)

_auth_rate_limit_store = defaultdict(list)

def check_auth_rate_limit(client_ip: str, max_requests: int = 5, window_seconds: int = 300) -> bool:
    now = time.time()
    requests = _auth_rate_limit_store[client_ip]
    requests[:] = [req_time for req_time in requests if now - req_time < window_seconds]
    if len(requests) >= max_requests:
        return False
    requests.append(now)
    return True


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    sub = payload.get("sub")
    if sub is None:
        raise credentials_exception
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise credentials_exception
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    if is_token_blocked(token):
        raise credentials_exception
    return user


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None
    payload = decode_access_token(token)
    if payload is None:
        return None
    sub = payload.get("sub")
    if sub is None:
        return None
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        return None
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        return None
    if is_token_blocked(token):
        return None
    return user


@router.post("/register", response_model=Token)
def register(request: Request, user_data: UserCreate, db: Session = Depends(get_db)):
    client_ip = request.client.host
    if not check_auth_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many registration attempts. Please try again later.")

    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user_data.password)
    user = User(email=user_data.email, hashed_password=hashed_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login", response_model=Token)
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    client_ip = request.client.host
    if not check_auth_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many login attempts. Please try again later.")

    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
def logout(token: str = Depends(oauth2_scheme)):
    block_token(token)
    return {"message": "Successfully logged out"}