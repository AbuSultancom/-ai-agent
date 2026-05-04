"""
E-commerce data models using SQLAlchemy with SQLite.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from enum import Enum as PyEnum

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def _new_id() -> str:
    return str(uuid.uuid4())


class OrderStatus(PyEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.String(36), primary_key=True, default=_new_id)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    products = db.relationship("Product", back_populates="category", lazy="dynamic")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "product_count": self.products.count(),
            "created_at": self.created_at.isoformat(),
        }


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.String(36), primary_key=True, default=_new_id)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, default=0)
    category_id = db.Column(db.String(36), db.ForeignKey("categories.id"), nullable=True)
    image_url = db.Column(db.String(500), default="")
    sku = db.Column(db.String(100), unique=True, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = db.relationship("Category", back_populates="products")
    order_items = db.relationship("OrderItem", back_populates="product", lazy="dynamic")

    def to_dict(self, include_category: bool = True) -> dict:
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "price": self.price,
            "stock": self.stock,
            "sku": self.sku,
            "image_url": self.image_url,
            "is_active": self.is_active,
            "category_id": self.category_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_category and self.category:
            data["category"] = self.category.name
        return data


class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.String(36), primary_key=True, default=_new_id)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=False, unique=True)
    phone = db.Column(db.String(30), default="")
    address = db.Column(db.Text, default="")
    city = db.Column(db.String(100), default="")
    country = db.Column(db.String(100), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    orders = db.relationship("Order", back_populates="customer", lazy="dynamic")
    carts = db.relationship("Cart", back_populates="customer", lazy="dynamic")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "city": self.city,
            "country": self.country,
            "order_count": self.orders.count(),
            "created_at": self.created_at.isoformat(),
        }


class Cart(db.Model):
    __tablename__ = "carts"

    id = db.Column(db.String(36), primary_key=True, default=_new_id)
    customer_id = db.Column(db.String(36), db.ForeignKey("customers.id"), nullable=True)
    session_id = db.Column(db.String(100), nullable=True)
    _items = db.Column("items", db.Text, default="[]")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = db.relationship("Customer", back_populates="carts")

    @property
    def items(self) -> list[dict]:
        return json.loads(self._items or "[]")

    @items.setter
    def items(self, value: list[dict]) -> None:
        self._items = json.dumps(value)

    def add_item(self, product_id: str, quantity: int, price: float, name: str) -> None:
        current = self.items
        for item in current:
            if item["product_id"] == product_id:
                item["quantity"] += quantity
                self.items = current
                return
        current.append({"product_id": product_id, "name": name, "quantity": quantity, "price": price})
        self.items = current

    def remove_item(self, product_id: str) -> bool:
        current = self.items
        new_items = [i for i in current if i["product_id"] != product_id]
        if len(new_items) == len(current):
            return False
        self.items = new_items
        return True

    def update_quantity(self, product_id: str, quantity: int) -> bool:
        current = self.items
        for item in current:
            if item["product_id"] == product_id:
                if quantity <= 0:
                    return self.remove_item(product_id)
                item["quantity"] = quantity
                self.items = current
                return True
        return False

    @property
    def total(self) -> float:
        return sum(i["price"] * i["quantity"] for i in self.items)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "customer_id": self.customer_id,
            "session_id": self.session_id,
            "items": self.items,
            "total": round(self.total, 2),
            "item_count": sum(i["quantity"] for i in self.items),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.String(36), primary_key=True, default=_new_id)
    order_number = db.Column(db.String(20), unique=True, nullable=False)
    customer_id = db.Column(db.String(36), db.ForeignKey("customers.id"), nullable=True)
    status = db.Column(db.String(20), default=OrderStatus.PENDING.value)
    subtotal = db.Column(db.Float, default=0.0)
    tax = db.Column(db.Float, default=0.0)
    shipping = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    shipping_address = db.Column(db.Text, default="")
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = db.relationship("Customer", back_populates="orders")
    items = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    def to_dict(self, include_items: bool = True) -> dict:
        data = {
            "id": self.id,
            "order_number": self.order_number,
            "customer_id": self.customer_id,
            "customer": self.customer.name if self.customer else None,
            "status": self.status,
            "subtotal": self.subtotal,
            "tax": self.tax,
            "shipping": self.shipping,
            "total": self.total,
            "shipping_address": self.shipping_address,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_items:
            data["items"] = [i.to_dict() for i in self.items]
        return data


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.String(36), primary_key=True, default=_new_id)
    order_id = db.Column(db.String(36), db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.String(36), db.ForeignKey("products.id"), nullable=True)
    product_name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)

    order = db.relationship("Order", back_populates="items")
    product = db.relationship("Product", back_populates="order_items")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "total_price": self.total_price,
        }
