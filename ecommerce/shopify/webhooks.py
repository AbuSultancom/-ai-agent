"""
Shopify webhook event processor.

Supported topics:
  orders/created        → save order to local DB, notify
  orders/updated        → sync order status
  orders/cancelled      → mark cancelled
  orders/fulfilled      → mark fulfilled
  products/create       → sync product to local DB
  products/update       → update local product
  products/delete       → deactivate local product
  inventory_levels/update → update local stock
  customers/create      → sync customer
  customers/update      → update customer
  app/uninstalled       → cleanup tokens
"""
from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_price(value: str | None) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


# ── handler registry ─────────────────────────────────────────────────────────

_HANDLERS: dict[str, callable] = {}


def _handler(topic: str):
    def decorator(fn):
        _HANDLERS[topic] = fn
        return fn
    return decorator


def process_webhook(topic: str, payload: dict) -> dict:
    """Dispatch a webhook payload to the appropriate handler."""
    fn = _HANDLERS.get(topic)
    if fn is None:
        logger.info("No handler for webhook topic: %s", topic)
        return {"status": "ignored", "topic": topic}
    try:
        result = fn(payload)
        return {"status": "ok", "topic": topic, "result": result}
    except Exception as e:
        logger.exception("Webhook handler failed for topic %s", topic)
        return {"status": "error", "topic": topic, "error": str(e)}


# ── order handlers ────────────────────────────────────────────────────────────

@_handler("orders/created")
def _order_created(payload: dict) -> dict:
    from ecommerce.models import db, Order, OrderItem, Customer
    from core.app import app

    with app.app_context():
        shopify_id = str(payload.get("id", ""))
        order_number = payload.get("name", shopify_id)

        # upsert customer
        customer_id = None
        c_data = payload.get("customer") or {}
        if c_data.get("email"):
            email = c_data["email"].lower()
            customer = Customer.query.filter_by(email=email).first()
            if not customer:
                customer = Customer(
                    name=f"{c_data.get('first_name', '')} {c_data.get('last_name', '')}".strip() or email,
                    email=email,
                    phone=c_data.get("phone", ""),
                )
                db.session.add(customer)
                db.session.flush()
            customer_id = customer.id

        # avoid duplicates
        if Order.query.filter_by(order_number=order_number).first():
            return {"skipped": "duplicate", "order_number": order_number}

        shipping_addr = payload.get("shipping_address") or {}
        addr_parts = [
            shipping_addr.get("address1", ""),
            shipping_addr.get("city", ""),
            shipping_addr.get("country", ""),
        ]
        shipping_address = ", ".join(p for p in addr_parts if p)

        subtotal = _parse_price(payload.get("subtotal_price"))
        tax = _parse_price(payload.get("total_tax"))
        shipping_cost = sum(
            _parse_price(s.get("price")) for s in payload.get("shipping_lines", [])
        )
        total = _parse_price(payload.get("total_price"))

        order = Order(
            order_number=order_number,
            customer_id=customer_id,
            status="confirmed",
            subtotal=subtotal,
            tax=tax,
            shipping=shipping_cost,
            total=total,
            shipping_address=shipping_address,
            notes=f"Shopify ID: {shopify_id}",
        )
        db.session.add(order)
        db.session.flush()

        for li in payload.get("line_items", []):
            oi = OrderItem(
                order_id=order.id,
                product_id=None,
                product_name=li.get("name", ""),
                quantity=int(li.get("quantity", 1)),
                unit_price=_parse_price(li.get("price")),
                total_price=_parse_price(li.get("price")) * int(li.get("quantity", 1)),
            )
            db.session.add(oi)

        db.session.commit()
        logger.info("Shopify order synced: %s", order_number)
        return {"order_id": order.id, "order_number": order_number}


@_handler("orders/updated")
def _order_updated(payload: dict) -> dict:
    from ecommerce.models import db, Order
    from core.app import app

    with app.app_context():
        order_number = payload.get("name", "")
        order = Order.query.filter_by(order_number=order_number).first()
        if not order:
            return {"skipped": "not_found", "order_number": order_number}

        fulfillment = payload.get("fulfillment_status")
        financial = payload.get("financial_status")

        if fulfillment == "fulfilled":
            order.status = "delivered"
        elif fulfillment == "partial":
            order.status = "processing"
        elif financial == "refunded":
            order.status = "refunded"
        elif payload.get("cancelled_at"):
            order.status = "cancelled"

        order.updated_at = datetime.utcnow()
        db.session.commit()
        return {"order_number": order_number, "new_status": order.status}


@_handler("orders/cancelled")
def _order_cancelled(payload: dict) -> dict:
    from ecommerce.models import db, Order
    from core.app import app

    with app.app_context():
        order_number = payload.get("name", "")
        order = Order.query.filter_by(order_number=order_number).first()
        if order:
            order.status = "cancelled"
            order.updated_at = datetime.utcnow()
            db.session.commit()
        return {"order_number": order_number}


@_handler("orders/fulfilled")
def _order_fulfilled(payload: dict) -> dict:
    from ecommerce.models import db, Order
    from core.app import app

    with app.app_context():
        order_number = payload.get("name", "")
        order = Order.query.filter_by(order_number=order_number).first()
        if order:
            order.status = "delivered"
            order.updated_at = datetime.utcnow()
            db.session.commit()
        return {"order_number": order_number}


# ── product handlers ──────────────────────────────────────────────────────────

def _shopify_product_to_local(payload: dict) -> dict:
    """Extract local-compatible fields from a Shopify product payload."""
    variant = (payload.get("variants") or [{}])[0]
    image = (payload.get("images") or [{}])[0]
    return {
        "name": payload.get("title", ""),
        "description": payload.get("body_html", ""),
        "price": _parse_price(variant.get("price")),
        "stock": int(variant.get("inventory_quantity") or 0),
        "sku": variant.get("sku", ""),
        "image_url": image.get("src", ""),
    }


@_handler("products/create")
def _product_created(payload: dict) -> dict:
    from ecommerce.models import db, Product
    from core.app import app

    with app.app_context():
        fields = _shopify_product_to_local(payload)
        sku = fields["sku"] or str(payload.get("id", ""))
        existing = Product.query.filter_by(sku=sku).first() if sku else None
        if existing:
            return {"skipped": "duplicate", "sku": sku}
        product = Product(**fields, sku=sku or None)
        db.session.add(product)
        db.session.commit()
        logger.info("Shopify product synced: %s", fields["name"])
        return {"product_id": product.id, "name": fields["name"]}


@_handler("products/update")
def _product_updated(payload: dict) -> dict:
    from ecommerce.models import db, Product
    from core.app import app

    with app.app_context():
        variant = (payload.get("variants") or [{}])[0]
        sku = variant.get("sku") or str(payload.get("id", ""))
        product = Product.query.filter_by(sku=sku).first()
        if not product:
            return _product_created(payload)

        fields = _shopify_product_to_local(payload)
        for k, v in fields.items():
            setattr(product, k, v)
        product.updated_at = datetime.utcnow()
        db.session.commit()
        return {"product_id": product.id, "name": fields["name"]}


@_handler("products/delete")
def _product_deleted(payload: dict) -> dict:
    from ecommerce.models import db, Product
    from core.app import app

    with app.app_context():
        shopify_id = str(payload.get("id", ""))
        product = Product.query.filter_by(sku=shopify_id).first()
        if product:
            product.is_active = False
            db.session.commit()
            return {"deactivated": product.id}
        return {"skipped": "not_found"}


# ── inventory handler ─────────────────────────────────────────────────────────

@_handler("inventory_levels/update")
def _inventory_updated(payload: dict) -> dict:
    from ecommerce.models import db, Product
    from core.app import app

    with app.app_context():
        available = payload.get("available")
        if available is None:
            return {"skipped": "no_available_field"}

        inventory_item_id = str(payload.get("inventory_item_id", ""))
        # find product by inventory_item_id stored as sku (best-effort)
        product = Product.query.filter_by(sku=inventory_item_id).first()
        if product:
            product.stock = int(available)
            product.updated_at = datetime.utcnow()
            db.session.commit()
            return {"product_id": product.id, "new_stock": available}
        return {"skipped": "product_not_found", "inventory_item_id": inventory_item_id}


# ── customer handlers ─────────────────────────────────────────────────────────

@_handler("customers/create")
def _customer_created(payload: dict) -> dict:
    from ecommerce.models import db, Customer
    from core.app import app

    with app.app_context():
        email = (payload.get("email") or "").lower()
        if not email:
            return {"skipped": "no_email"}
        if Customer.query.filter_by(email=email).first():
            return {"skipped": "duplicate", "email": email}
        addr = (payload.get("addresses") or [{}])[0]
        customer = Customer(
            name=f"{payload.get('first_name', '')} {payload.get('last_name', '')}".strip() or email,
            email=email,
            phone=payload.get("phone", ""),
            address=addr.get("address1", ""),
            city=addr.get("city", ""),
            country=addr.get("country", ""),
        )
        db.session.add(customer)
        db.session.commit()
        return {"customer_id": customer.id, "email": email}


@_handler("customers/update")
def _customer_updated(payload: dict) -> dict:
    from ecommerce.models import db, Customer
    from core.app import app

    with app.app_context():
        email = (payload.get("email") or "").lower()
        customer = Customer.query.filter_by(email=email).first()
        if not customer:
            return _customer_created(payload)
        addr = (payload.get("addresses") or [{}])[0]
        customer.name = f"{payload.get('first_name', '')} {payload.get('last_name', '')}".strip() or customer.name
        customer.phone = payload.get("phone", customer.phone)
        customer.address = addr.get("address1", customer.address)
        customer.city = addr.get("city", customer.city)
        customer.country = addr.get("country", customer.country)
        db.session.commit()
        return {"customer_id": customer.id, "email": email}


@_handler("app/uninstalled")
def _app_uninstalled(payload: dict) -> dict:
    logger.warning("Shopify app uninstalled for shop: %s", payload.get("domain"))
    return {"shop": payload.get("domain")}
