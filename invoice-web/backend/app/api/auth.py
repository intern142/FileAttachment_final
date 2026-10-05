from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Form, Request, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import JWTError

from ..core.config import get_settings
from ..core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    decode_access_token,
)
from ..models import User
from ..schemas import UserCreate, UserLogin, Token, TokenData
from ..database import get_db

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

_token_blocklist: set[str] = set()


def set_auth_cookie(response: Response, token: str):
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


def get_db_session():
    db = next(get_db())
    try:
        yield db
    finally:
        db.close()


def is_token_revoked(token: str) -> bool:
    return token in _token_blocklist


def revoke_token(token: str):
    _token_blocklist.add(token)


def check_rate_limit(client_ip: str, max_requests: int = 5, window_seconds: int = 300) -> bool:
    if not hasattr(check_rate_limit, "_store"):
        check_rate_limit._store = {}
    now = __import__("time").time()
    store = check_rate_limit._store
    requests = store.get(client_ip, [])
    requests = [req_time for req_time in requests if now - req_time < window_seconds]
    if len(requests) >= max_requests:
        return False
    requests.append(now)
    store[client_ip] = requests
    return True


@router.post("/register", response_model=Token)
def register(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db_session),
):
    client_ip = request.client.host
    if not check_rate_limit(client_ip, max_requests=3, window_seconds=3600):
        raise HTTPException(status_code=429, detail="Too many registration attempts. Try again later.")

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(email=email, hashed_password=get_password_hash(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    set_auth_cookie(response, access_token)
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login", response_model=Token)
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db_session),
):
    client_ip = request.client.host
    if not check_rate_limit(client_ip, max_requests=5, window_seconds=300):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")

    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    set_auth_cookie(response, access_token)
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
):
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
    if token:
        revoke_token(token)
    response.delete_cookie("access_token", path="/")
    return {"message": "Logged out successfully"}


def get_current_user(
    request: Request,
    db: Session = Depends(get_db_session),
    header_token: Optional[str] = Depends(oauth2_scheme),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = header_token or request.cookies.get("access_token")
    if not token:
        raise credentials_exception
    if is_token_revoked(token):
        raise HTTPException(status_code=401, detail="Token has been revoked")
    payload = decode_access_token(token)
    if not payload:
        raise credentials_exception
    user_id: str = payload.get("sub")
    if not user_id:
        raise credentials_exception
    token_data = TokenData(user_id=int(user_id))
    user = db.query(User).filter(User.id == token_data.user_id).first()
    if not user:
        raise credentials_exception
    return user


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db_session),
) -> Optional[User]:
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        return None
    if is_token_revoked(token):
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    return db.query(User).filter(User.id == int(user_id)).first()