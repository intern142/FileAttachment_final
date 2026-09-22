from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
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


class ContractorResponse(ContractorBase):
    id: int

    class Config:
        from_attributes = True


class SourceBase(BaseModel):
    name: str
    short_code: str


class SourceCreate(SourceBase):
    pass


class SourceResponse(SourceBase):
    id: int

    class Config:
        from_attributes = True


class InvoiceBase(BaseModel):
    contractor_id: int
    source_id: int
    date: datetime
    amount: Decimal


class InvoiceCreate(InvoiceBase):
    file_path: str
    ocr_json: Optional[str] = None


class InvoiceUpdate(BaseModel):
    contractor_id: Optional[int] = None
    source_id: Optional[int] = None
    date: Optional[datetime] = None
    amount: Optional[Decimal] = None


class InvoiceResponse(InvoiceBase):
    id: int
    user_id: int
    file_path: str
    ocr_json: Optional[str] = None
    status: str
    created_at: datetime
    contractor: ContractorResponse
    source: SourceResponse

    class Config:
        from_attributes = True


class InvoiceListItem(BaseModel):
    id: int
    date: datetime
    amount: Decimal
    contractor_name: str
    contractor_short: str
    source_name: str
    source_short: str
    file_path: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class OCRResult(BaseModel):
    job_id: str
    text: str
    contractor: Optional[str] = None
    source: Optional[str] = None
    date: Optional[str] = None
    amount: Optional[str] = None


class ConfirmRequest(BaseModel):
    job_id: str
    contractor_id: int
    source_id: int
    date: str
    amount: str


class InvoiceFilters(BaseModel):
    contractor_id: Optional[int] = None
    source_id: Optional[int] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    page: int = 1
    per_page: int = 20