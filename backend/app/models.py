from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Enum, Text, Numeric, Index
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class InvoiceStatus(str, PyEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    invoices = relationship("Invoice", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")


class Contractor(Base):
    __tablename__ = "contractors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    short_code = Column(String(10), unique=True, nullable=False)

    invoices = relationship("Invoice", back_populates="contractor")


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    short_code = Column(String(10), unique=True, nullable=False)

    invoices = relationship("Invoice", back_populates="source")


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    contractor_id = Column(Integer, ForeignKey("contractors.id"), nullable=False)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    date = Column(DateTime, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    file_path = Column(String(500), nullable=False)
    ocr_json = Column(Text, nullable=True)
    status = Column(Enum(InvoiceStatus), default=InvoiceStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="invoices")
    contractor = relationship("Contractor", back_populates="invoices")
    source = relationship("Source", back_populates="invoices")
    audit_logs = relationship("AuditLog", back_populates="invoice")

    __table_args__ = (
        Index("ix_invoices_user_date", "user_id", "date"),
        Index("ix_invoices_contractor_date", "contractor_id", "date"),
        Index("ix_invoices_source_date", "source_id", "date"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    action = Column(String(50), nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="audit_logs")
    invoice = relationship("Invoice", back_populates="audit_logs")