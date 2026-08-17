"""initial postgres schema

Revision ID: b7f3c9a21d04
Revises:
Create Date: 2026-08-17 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7f3c9a21d04'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'roles',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=20), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    op.create_table(
        'users',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=False),
        sa.Column('role_id', sa.Uuid(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_role_id'), 'users', ['role_id'], unique=False)

    op.create_table(
        'categories',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(length=1000), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    op.create_table(
        'suppliers',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('address', sa.String(length=1000), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_suppliers_email'), 'suppliers', ['email'], unique=True)

    op.create_table(
        'notifications',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column(
            'type',
            sa.Enum('LOW_STOCK', 'OUT_OF_STOCK', 'PURCHASE_COMPLETED', 'SALE_COMPLETED',
                    name='notificationtype', native_enum=False, length=30),
            nullable=False,
        ),
        sa.Column('message', sa.String(length=1000), nullable=False),
        sa.Column('reference_id', sa.Uuid(), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)

    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('token', sa.String(length=512), nullable=False),
        sa.Column('revoked', sa.Boolean(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_refresh_tokens_token'), 'refresh_tokens', ['token'], unique=True)
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)

    op.create_table(
        'products',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('sku', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(length=2000), nullable=True),
        sa.Column('cost_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('selling_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('current_stock', sa.Integer(), nullable=False),
        sa.Column('low_stock_threshold', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.Uuid(), nullable=False),
        sa.Column('supplier_id', sa.Uuid(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_products_sku'), 'products', ['sku'], unique=True)
    op.create_index(op.f('ix_products_name'), 'products', ['name'], unique=False)
    op.create_index(op.f('ix_products_selling_price'), 'products', ['selling_price'], unique=False)
    op.create_index(op.f('ix_products_current_stock'), 'products', ['current_stock'], unique=False)
    op.create_index(op.f('ix_products_category_id'), 'products', ['category_id'], unique=False)
    op.create_index(op.f('ix_products_supplier_id'), 'products', ['supplier_id'], unique=False)

    op.create_table(
        'purchase_orders',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('supplier_id', sa.Uuid(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('ORDERED', 'RECEIVED', name='purchaseorderstatus', native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_purchase_orders_supplier_id'), 'purchase_orders', ['supplier_id'], unique=False)
    op.create_index(op.f('ix_purchase_orders_status'), 'purchase_orders', ['status'], unique=False)
    op.create_index(op.f('ix_purchase_orders_created_at'), 'purchase_orders', ['created_at'], unique=False)

    op.create_table(
        'purchase_order_items',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('purchase_order_id', sa.Uuid(), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit_cost', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_purchase_order_items_purchase_order_id'), 'purchase_order_items', ['purchase_order_id'],
        unique=False,
    )
    op.create_index(op.f('ix_purchase_order_items_product_id'), 'purchase_order_items', ['product_id'], unique=False)

    op.create_table(
        'sales_orders',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('CREATED', 'COMPLETED', name='salesorderstatus', native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column('customer_name', sa.String(length=255), nullable=True),
        sa.Column('customer_phone', sa.String(length=50), nullable=True),
        sa.Column('invoice_number', sa.String(length=50), nullable=True),
        sa.Column('invoiced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('invoice_number'),
    )
    op.create_index(op.f('ix_sales_orders_status'), 'sales_orders', ['status'], unique=False)
    op.create_index(op.f('ix_sales_orders_created_at'), 'sales_orders', ['created_at'], unique=False)

    op.create_table(
        'sales_order_items',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('sales_order_id', sa.Uuid(), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.ForeignKeyConstraint(['sales_order_id'], ['sales_orders.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sales_order_items_sales_order_id'), 'sales_order_items', ['sales_order_id'], unique=False)
    op.create_index(op.f('ix_sales_order_items_product_id'), 'sales_order_items', ['product_id'], unique=False)

    op.create_table(
        'inventory_transactions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column(
            'transaction_type',
            sa.Enum('PURCHASE', 'SALE', 'RETURN', 'DAMAGE', name='transactiontype', native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column('reference_id', sa.Uuid(), nullable=True),
        sa.Column('reason', sa.String(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_inventory_transactions_product_id'), 'inventory_transactions', ['product_id'], unique=False
    )
    op.create_index(
        op.f('ix_inventory_transactions_transaction_type'), 'inventory_transactions', ['transaction_type'],
        unique=False,
    )
    op.create_index(
        op.f('ix_inventory_transactions_created_at'), 'inventory_transactions', ['created_at'], unique=False
    )
    op.create_index(
        op.f('ix_inventory_transactions_created_by'), 'inventory_transactions', ['created_by'], unique=False
    )

    op.create_table(
        'returns',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('sales_order_id', sa.Uuid(), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=1000), nullable=False),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'APPROVED', name='returnstatus', native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column('approved_by', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.ForeignKeyConstraint(['sales_order_id'], ['sales_orders.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_returns_sales_order_id'), 'returns', ['sales_order_id'], unique=False)
    op.create_index(op.f('ix_returns_product_id'), 'returns', ['product_id'], unique=False)
    op.create_index(op.f('ix_returns_status'), 'returns', ['status'], unique=False)
    op.create_index(op.f('ix_returns_approved_by'), 'returns', ['approved_by'], unique=False)
    op.create_index(op.f('ix_returns_created_at'), 'returns', ['created_at'], unique=False)
    op.create_index(op.f('ix_returns_created_by'), 'returns', ['created_by'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('returns')
    op.drop_index(op.f('ix_inventory_transactions_created_by'), table_name='inventory_transactions')
    op.drop_index(op.f('ix_inventory_transactions_created_at'), table_name='inventory_transactions')
    op.drop_index(op.f('ix_inventory_transactions_transaction_type'), table_name='inventory_transactions')
    op.drop_index(op.f('ix_inventory_transactions_product_id'), table_name='inventory_transactions')
    op.drop_table('inventory_transactions')
    op.drop_index(op.f('ix_sales_order_items_product_id'), table_name='sales_order_items')
    op.drop_index(op.f('ix_sales_order_items_sales_order_id'), table_name='sales_order_items')
    op.drop_table('sales_order_items')
    op.drop_index(op.f('ix_sales_orders_created_at'), table_name='sales_orders')
    op.drop_index(op.f('ix_sales_orders_status'), table_name='sales_orders')
    op.drop_table('sales_orders')
    op.drop_index(op.f('ix_purchase_order_items_product_id'), table_name='purchase_order_items')
    op.drop_index(op.f('ix_purchase_order_items_purchase_order_id'), table_name='purchase_order_items')
    op.drop_table('purchase_order_items')
    op.drop_index(op.f('ix_purchase_orders_created_at'), table_name='purchase_orders')
    op.drop_index(op.f('ix_purchase_orders_status'), table_name='purchase_orders')
    op.drop_index(op.f('ix_purchase_orders_supplier_id'), table_name='purchase_orders')
    op.drop_table('purchase_orders')
    op.drop_index(op.f('ix_products_supplier_id'), table_name='products')
    op.drop_index(op.f('ix_products_category_id'), table_name='products')
    op.drop_index(op.f('ix_products_current_stock'), table_name='products')
    op.drop_index(op.f('ix_products_selling_price'), table_name='products')
    op.drop_index(op.f('ix_products_name'), table_name='products')
    op.drop_index(op.f('ix_products_sku'), table_name='products')
    op.drop_table('products')
    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_token'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_index(op.f('ix_notifications_user_id'), table_name='notifications')
    op.drop_table('notifications')
    op.drop_index(op.f('ix_suppliers_email'), table_name='suppliers')
    op.drop_table('suppliers')
    op.drop_table('categories')
    op.drop_index(op.f('ix_users_role_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_table('roles')
