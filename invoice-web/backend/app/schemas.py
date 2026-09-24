from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict


class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[int] = None


class ContractorBase(BaseModel):
    name: str
    short_code: str


class ContractorCreate(ContractorBase):
    pass


class ContractorOut(ContractorBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class SourceBase(BaseModel):
    name: str
    short_code: str


class SourceCreate(SourceBase):
    pass


class SourceOut(SourceBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class InvoiceBase(BaseModel):
    contractor_id: int
    source_id: int
    date: datetime
    amount: Decimal
    file_path: str
    ocr_json: Optional[str] = None


class InvoiceCreate(InvoiceBase):
    pass


class InvoiceUpdate(BaseModel):
    contractor_id: Optional[int] = None
    source_id: Optional[int] = None
    date: Optional[datetime] = None
    amount: Optional[Decimal] = None


class InvoiceOut(InvoiceBase):
    id: int
    user_id: int
    status: str
    created_at: datetime
    updated_at: datetime
    contractor: Optional[ContractorOut] = None
    source: Optional[SourceOut] = None
    model_config = ConfigDict(from_attributes=True)


class InvoiceListParams(BaseModel):
    contractor_id: Optional[int] = None
    source_id: Optional[int] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    page: int = 1
    page_size: int = 20


class OCRResult(BaseModel):
    job_id: str
    text: str
    contractor: Optional[str] = None
    source: Optional[str] = None
    date: Optional[str] = None
    amount: Optional[str] = None


class ExtractResult(BaseModel):
    contractor: str
    purchased_from: str
    date: str
    filename: str
    invoice_id: int
    saved: bool = True


class RenameRequest(BaseModel):
    invoice_id: int
    contractor: str
    purchased_from: str


class RenameResult(BaseModel):
    invoice_id: int
    filename: str
    path: str
    url: str
    saved: bool = True


class ConfirmRequest(BaseModel):
    job_id: str
    contractor_id: int
    source_id: int
    date: datetime
    amount: Decimal