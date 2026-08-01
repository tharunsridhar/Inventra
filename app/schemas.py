"""All the Pydantic request/response models, in one file."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import (
    NotificationType,
    PurchaseOrderStatus,
    ReturnStatus,
    RoleName,
    SalesOrderStatus,
    TransactionType,
)

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


# --------------------------------------------------------------- auth ----

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# -------------------------------------------------------------- users ----

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=255)
    role: RoleName


class UserUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None


class AssignRoleRequest(BaseModel):
    role: RoleName


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8)


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime


def user_to_read(user) -> UserRead:
    return UserRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.name,
        is_active=user.is_active,
        created_at=user.created_at,
    )


# --------------------------------------------------------- categories ----

class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class CategoryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: str | None
    is_active: bool
    created_at: datetime


# ---------------------------------------------------------- suppliers ----

class SupplierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    phone: str | None = None
    address: str | None = None


class SupplierUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None


class SupplierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    email: str
    phone: str | None
    address: str | None
    is_active: bool
    created_at: datetime


# ----------------------------------------------------------- products ----

class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    cost_price: Decimal = Field(max_digits=10, decimal_places=2, ge=0)
    selling_price: Decimal = Field(max_digits=10, decimal_places=2, ge=0)
    current_stock: int = Field(default=0, ge=0)
    low_stock_threshold: int = Field(default=0, ge=0)
    category_id: uuid.UUID
    supplier_id: uuid.UUID


class ProductUpdate(BaseModel):
    sku: str | None = None
    name: str | None = None
    description: str | None = None
    cost_price: Decimal | None = Field(default=None, max_digits=10, decimal_places=2, ge=0)
    selling_price: Decimal | None = Field(default=None, max_digits=10, decimal_places=2, ge=0)
    low_stock_threshold: int | None = Field(default=None, ge=0)
    category_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    sku: str
    name: str
    description: str | None
    cost_price: Decimal
    selling_price: Decimal
    current_stock: int
    low_stock_threshold: int
    category_id: uuid.UUID
    supplier_id: uuid.UUID
    is_active: bool
    created_at: datetime


# --------------------------------------------------------- purchases ----

class PurchaseOrderItemCreate(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0)
    unit_cost: Decimal = Field(max_digits=10, decimal_places=2, ge=0)


class PurchaseOrderCreate(BaseModel):
    supplier_id: uuid.UUID
    items: list[PurchaseOrderItemCreate] = Field(min_length=1)


class PurchaseOrderUpdate(BaseModel):
    supplier_id: uuid.UUID | None = None
    items: list[PurchaseOrderItemCreate] | None = Field(default=None, min_length=1)


class PurchaseOrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    unit_cost: Decimal


class PurchaseOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    supplier_id: uuid.UUID
    status: PurchaseOrderStatus
    received_at: datetime | None
    items: list[PurchaseOrderItemRead]
    created_by: uuid.UUID | None
    created_at: datetime


# ------------------------------------------------------------- sales ----

class SalesOrderItemCreate(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0)


class SalesOrderCreate(BaseModel):
    customer_name: str | None = None
    customer_phone: str | None = None
    items: list[SalesOrderItemCreate] = Field(min_length=1)


class SalesOrderUpdate(BaseModel):
    customer_name: str | None = None
    customer_phone: str | None = None
    items: list[SalesOrderItemCreate] | None = Field(default=None, min_length=1)


class SalesOrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    unit_price: Decimal


class SalesOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: SalesOrderStatus
    customer_name: str | None
    customer_phone: str | None
    invoice_number: str | None
    invoiced_at: datetime | None
    items: list[SalesOrderItemRead]
    created_by: uuid.UUID | None
    created_at: datetime


class InvoiceRead(BaseModel):
    sales_order_id: uuid.UUID
    invoice_number: str
    invoiced_at: datetime
    customer_name: str | None
    customer_phone: str | None
    items: list[SalesOrderItemRead]
    total_amount: Decimal


# ----------------------------------------------------------- returns ----

class ReturnCreate(BaseModel):
    sales_order_id: uuid.UUID
    product_id: uuid.UUID
    quantity: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=1000)


class ReturnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    sales_order_id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    reason: str
    status: ReturnStatus
    approved_by: uuid.UUID | None
    created_by: uuid.UUID | None
    created_at: datetime


# ------------------------------------------------------------ damage ----

class DamageWriteOffCreate(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=1000)


# ------------------------------------------------- inventory txns ----

class InventoryTransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    transaction_type: TransactionType
    reference_id: uuid.UUID | None
    reason: str | None
    created_by: uuid.UUID | None
    created_at: datetime


# -------------------------------------------------------- dashboard ----

class DashboardRead(BaseModel):
    total_products: int
    total_categories: int
    total_suppliers: int
    total_users: int
    total_purchases: int
    total_sales: int
    low_stock_products: int
    out_of_stock_products: int


# ----------------------------------------------------------- reports ----

class ReportMeta(BaseModel):
    generated_at: datetime
    start_date: datetime | None
    end_date: datetime | None


class ProductReportItem(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    category_id: uuid.UUID
    supplier_id: uuid.UUID
    cost_price: Decimal
    selling_price: Decimal
    current_stock: int
    low_stock_threshold: int
    is_active: bool


class ProductReport(ReportMeta):
    total_count: int
    items: list[ProductReportItem]


class PurchaseReportItem(BaseModel):
    id: uuid.UUID
    supplier_id: uuid.UUID
    status: PurchaseOrderStatus
    created_at: datetime
    total_cost: Decimal


class PurchaseReport(ReportMeta):
    total_orders: int
    total_cost: Decimal
    items: list[PurchaseReportItem]


class SalesReportItem(BaseModel):
    id: uuid.UUID
    status: SalesOrderStatus
    created_at: datetime
    invoice_number: str | None
    total_amount: Decimal


class SalesReport(ReportMeta):
    total_orders: int
    total_revenue: Decimal
    items: list[SalesReportItem]


class InventoryReportSummary(BaseModel):
    total_purchased: int
    total_sold: int
    total_returned: int
    total_damaged: int


class InventoryReportItem(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    transaction_type: TransactionType
    reference_id: uuid.UUID | None
    reason: str | None
    created_at: datetime


class InventoryReport(ReportMeta):
    summary: InventoryReportSummary
    transactions: list[InventoryReportItem]


# ------------------------------------------------------ notifications ----

class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    type: NotificationType
    message: str
    reference_id: uuid.UUID | None
    is_read: bool
    created_at: datetime
