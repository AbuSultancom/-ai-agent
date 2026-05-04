"""
Two-way sync between the local SQLite e-commerce DB and Shopify.

Pull  → import Shopify data into local DB  (Shopify is source of truth)
Push  → export local products to Shopify   (local is source of truth)
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ─── Pull: Shopify → local ────────────────────────────────────────────────────

def pull_products(limit: int = 250) -> dict[str, Any]:
    """Import all active Shopify products into local DB."""
    from ecommerce.shopify.client import get_client
    from ecommerce.models import db, Product, Category
    from core.app import app

    client = get_client()
    created = updated = skipped = 0
    page_info = None

    with app.app_context():
        while True:
            resp = client.list_products(limit=250, page_info=page_info)
            products = resp.get("products", [])
            if not products:
                break

            for sp in products:
                variant = (sp.get("variants") or [{}])[0]
                image = (sp.get("images") or [{}])[0]
                sku = variant.get("sku") or str(sp["id"])
                price = float(variant.get("price") or 0)
                stock = int(variant.get("inventory_quantity") or 0)

                # ensure category exists
                cat_name = sp.get("product_type") or "General"
                cat = Category.query.filter_by(name=cat_name).first()
                if not cat:
                    cat = Category(name=cat_name)
                    db.session.add(cat)
                    db.session.flush()

                existing = Product.query.filter_by(sku=sku).first()
                if existing:
                    existing.name = sp.get("title", existing.name)
                    existing.description = sp.get("body_html", existing.description)
                    existing.price = price
                    existing.stock = stock
                    existing.image_url = image.get("src", existing.image_url)
                    existing.category_id = cat.id
                    updated += 1
                else:
                    p = Product(
                        name=sp.get("title", ""),
                        description=sp.get("body_html", ""),
                        price=price,
                        stock=stock,
                        sku=sku,
                        image_url=image.get("src", ""),
                        category_id=cat.id,
                    )
                    db.session.add(p)
                    created += 1

            db.session.commit()

            # Shopify cursor-based pagination
            link = resp.get("link") or ""
            if 'rel="next"' in link:
                import re
                match = re.search(r'page_info=([^&>]+)', link.split('rel="next"')[0])
                page_info = match.group(1) if match else None
            else:
                page_info = None

            if not page_info:
                break

    return {"created": created, "updated": updated, "skipped": skipped}


def pull_customers(limit: int = 250) -> dict[str, Any]:
    """Import Shopify customers into local DB."""
    from ecommerce.shopify.client import get_client
    from ecommerce.models import db, Customer
    from core.app import app

    client = get_client()
    created = updated = 0

    with app.app_context():
        resp = client.list_customers(limit=limit)
        for sc in resp.get("customers", []):
            email = (sc.get("email") or "").lower()
            if not email:
                continue
            addr = (sc.get("addresses") or [{}])[0]
            name = f"{sc.get('first_name', '')} {sc.get('last_name', '')}".strip() or email
            existing = Customer.query.filter_by(email=email).first()
            if existing:
                existing.name = name
                existing.phone = sc.get("phone", existing.phone)
                updated += 1
            else:
                c = Customer(
                    name=name,
                    email=email,
                    phone=sc.get("phone", ""),
                    address=addr.get("address1", ""),
                    city=addr.get("city", ""),
                    country=addr.get("country", ""),
                )
                db.session.add(c)
                created += 1
        db.session.commit()

    return {"created": created, "updated": updated}


def pull_orders(limit: int = 250, status: str = "any") -> dict[str, Any]:
    """Import recent Shopify orders into local DB."""
    from ecommerce.shopify.client import get_client
    from ecommerce.models import db, Order, OrderItem, Customer
    from core.app import app

    client = get_client()
    created = skipped = 0

    with app.app_context():
        resp = client.list_orders(status=status, limit=limit)
        for so in resp.get("orders", []):
            order_number = so.get("name", str(so["id"]))
            if Order.query.filter_by(order_number=order_number).first():
                skipped += 1
                continue

            customer_id = None
            c_data = so.get("customer") or {}
            if c_data.get("email"):
                email = c_data["email"].lower()
                cust = Customer.query.filter_by(email=email).first()
                if not cust:
                    cust = Customer(
                        name=f"{c_data.get('first_name', '')} {c_data.get('last_name', '')}".strip() or email,
                        email=email,
                        phone=c_data.get("phone", ""),
                    )
                    db.session.add(cust)
                    db.session.flush()
                customer_id = cust.id

            shipping_addr = so.get("shipping_address") or {}
            shipping_address = ", ".join(filter(None, [
                shipping_addr.get("address1"),
                shipping_addr.get("city"),
                shipping_addr.get("country"),
            ]))

            fulfillment = so.get("fulfillment_status")
            financial = so.get("financial_status")
            if so.get("cancelled_at"):
                status_local = "cancelled"
            elif fulfillment == "fulfilled":
                status_local = "delivered"
            elif fulfillment == "partial":
                status_local = "processing"
            elif financial == "refunded":
                status_local = "refunded"
            else:
                status_local = "confirmed"

            order = Order(
                order_number=order_number,
                customer_id=customer_id,
                status=status_local,
                subtotal=float(so.get("subtotal_price") or 0),
                tax=float(so.get("total_tax") or 0),
                shipping=sum(float(s.get("price", 0)) for s in so.get("shipping_lines", [])),
                total=float(so.get("total_price") or 0),
                shipping_address=shipping_address,
                notes=f"Shopify ID: {so['id']}",
            )
            db.session.add(order)
            db.session.flush()

            for li in so.get("line_items", []):
                price = float(li.get("price") or 0)
                qty = int(li.get("quantity") or 1)
                oi = OrderItem(
                    order_id=order.id,
                    product_id=None,
                    product_name=li.get("name", ""),
                    quantity=qty,
                    unit_price=price,
                    total_price=round(price * qty, 2),
                )
                db.session.add(oi)

            created += 1

        db.session.commit()

    return {"created": created, "skipped": skipped}


def pull_all() -> dict[str, Any]:
    """Run full sync: products → customers → orders."""
    products = pull_products()
    customers = pull_customers()
    orders = pull_orders()
    return {"products": products, "customers": customers, "orders": orders}


# ─── Push: local → Shopify ────────────────────────────────────────────────────

def push_product(product_id: str) -> dict[str, Any]:
    """Export a single local product to Shopify (creates or updates)."""
    from ecommerce.shopify.client import get_client
    from ecommerce.models import Product
    from core.app import app

    client = get_client()

    with app.app_context():
        product = Product.query.get(product_id)
        if not product:
            return {"error": "product not found"}

        payload = {
            "title": product.name,
            "body_html": product.description,
            "variants": [{"price": str(product.price), "sku": product.sku or "", "inventory_quantity": product.stock}],
        }
        if product.image_url:
            payload["images"] = [{"src": product.image_url}]

        if product.sku:
            existing = client.list_products(status="any", **{"sku": product.sku}).get("products", [])
            if existing:
                shopify_id = existing[0]["id"]
                result = client.update_product(shopify_id, **payload)
                return {"action": "updated", "shopify_id": shopify_id}

        result = client.create_product(**payload)
        shopify_product = result.get("product", {})
        return {"action": "created", "shopify_id": shopify_product.get("id")}


def push_all_products() -> dict[str, Any]:
    """Export all active local products to Shopify."""
    from ecommerce.models import Product
    from core.app import app

    created = updated = errors = 0

    with app.app_context():
        products = Product.query.filter_by(is_active=True).all()
        ids = [p.id for p in products]

    for pid in ids:
        try:
            result = push_product(pid)
            if result.get("action") == "created":
                created += 1
            else:
                updated += 1
        except Exception as e:
            logger.error("Failed to push product %s: %s", pid, e)
            errors += 1

    return {"created": created, "updated": updated, "errors": errors}
