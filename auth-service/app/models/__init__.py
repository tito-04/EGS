from sqlalchemy import String, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, MappedColumn, mapped_column
from sqlalchemy.sql import func
from uuid import uuid4
import enum as py_enum


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class RoleEnum(py_enum.Enum):
    """User role enumeration."""
    FAN = "fan"
    PROMOTER = "promoter"
    ADMIN = "admin"


class User(Base):
    """User database model."""
    __tablename__ = "users"
    
    id: MappedColumn[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: MappedColumn[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: MappedColumn[str] = mapped_column(String(255), nullable=False)
    hashed_password: MappedColumn[str] = mapped_column(String(255), nullable=False)
    is_active: MappedColumn[bool] = mapped_column(Boolean, default=True, nullable=False)
    role: MappedColumn[RoleEnum] = mapped_column(SQLEnum(RoleEnum), default=RoleEnum.FAN, nullable=False)
    created_at: MappedColumn[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: MappedColumn[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"
