"""
Public storefront API — serves the bilingual website.
/store/*          HTML pages
/api/store/*      JSON data for the frontend
"""
from __future__ import annotations
import logging
from flask import Blueprint, jsonify, render_template, request

logger = logging.getLogger(__name__)
store_bp = Blueprint("store", __name__)


def _ok(data=None, **extra):
    p = {"success": True}
    if data is not None:
        p["data"] = data
    p.update(extra)
    return jsonify(p)


def _err(msg: str, status: int = 400):
    return jsonify({"success": False, "error": msg}), status


# ── HTML pages ────────────────────────────────────────────────────────────────

@store_bp.route("/store")
@store_bp.route("/store/")
def store_home():
    return render_template("store/index.html")


@store_bp.route("/store/products")
def store_products():
    return render_template("store/products.html")


@store_bp.route("/store/products/<product_id>")
def store_product_detail(product_id: str):
    return render_template("store/product.html", product_id=product_id)


@store_bp.route("/store/cart")
def store_cart():
    return render_template("store/cart.html")


@store_bp.route("/store/checkout")
def store_checkout():
    return render_template("store/checkout.html")


@store_bp.route("/store/order-success")
def store_order_success():
    return render_template("store/order_success.html")


# ── JSON API ──────────────────────────────────────────────────────────────────

@store_bp.route("/api/store/products", methods=["GET"])
def api_products():
    search   = request.args.get("search", "")
    source   = request.args.get("source")
    limit    = min(int(request.args.get("limit", 60)), 200)
    page     = int(request.args.get("page", 1))
    min_p    = request.args.get("min_price", type=float)
    max_p    = request.args.get("max_price", type=float)
    category = request.args.get("category", "")

    from ecommerce.unified import get_all_products
    products = get_all_products(search=search, limit=limit * page, source_filter=source)

    if min_p is not None:
        products = [p for p in products if p["price"] >= min_p]
    if max_p is not None:
        products = [p for p in products if p["price"] <= max_p]
    if category:
        products = [p for p in products if category.lower() in p["category"].lower()]

    total = len(products)
    start = (page - 1) * limit
    end   = start + limit
    return _ok(products[start:end], total=total, page=page,
               pages=(total + limit - 1) // limit if limit else 1)


@store_bp.route("/api/store/products/<product_id>", methods=["GET"])
def api_product_detail(product_id: str):
    from ecommerce.models import Product
    p = Product.query.get(product_id)
    if not p:
        return _err("Product not found", 404)
    data = p.to_dict()
    # related products (same category)
    related = Product.query.filter(
        Product.category_id == p.category_id,
        Product.id != p.id,
        Product.is_active == True,
    ).limit(4).all()
    data["related"] = [r.to_dict() for r in related]
    return _ok(data)


@store_bp.route("/api/store/summary", methods=["GET"])
def api_summary():
    from ecommerce.unified import get_store_summary
    return _ok(get_store_summary())


@store_bp.route("/api/store/sources", methods=["GET"])
def api_sources():
    from ecommerce.unified import enabled_sources
    return _ok(enabled_sources())


@store_bp.route("/api/store/checkout", methods=["POST"])
def api_checkout():
    """Process checkout from the storefront."""
    body = request.get_json(silent=True) or {}
    customer_data = body.get("customer", {})
    cart_items    = body.get("items", [])
    shipping_addr = body.get("shipping_address", "")

    if not cart_items:
        return _err("Cart is empty")
    if not customer_data.get("email"):
        return _err("Customer email is required")

    from ecommerce.models import db, Cart, Customer, Order, OrderItem
    import uuid

    # upsert customer
    email = customer_data["email"].strip().lower()
    customer = Customer.query.filter_by(email=email).first()
    if not customer:
        customer = Customer(
            name=customer_data.get("name", email),
            email=email,
            phone=customer_data.get("phone", ""),
            address=shipping_addr,
        )
        db.session.add(customer)
        db.session.flush()

    # validate items + calculate total
    from ecommerce.models import Product
    subtotal = 0.0
    order_items = []
    for item in cart_items:
        product = Product.query.get(item.get("product_id"))
        if not product or not product.is_active:
            return _err(f"Product not available: {item.get('name', item.get('product_id'))}")
        qty = int(item.get("quantity", 1))
        if product.stock < qty:
            return _err(f"Insufficient stock for: {product.name}")
        price = product.price
        subtotal += price * qty
        order_items.append({"product": product, "qty": qty, "price": price})

    tax      = round(subtotal * 0.15, 2)
    shipping = float(body.get("shipping_cost", 0))
    total    = round(subtotal + tax + shipping, 2)

    from datetime import datetime, timezone
    from random import randint
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    order_number = f"WEB-{ts}-{randint(100, 999)}"

    order = Order(
        order_number=order_number,
        customer_id=customer.id,
        status="confirmed",
        subtotal=round(subtotal, 2),
        tax=tax,
        shipping=shipping,
        total=total,
        shipping_address=shipping_addr,
        notes=body.get("notes", ""),
    )
    db.session.add(order)
    db.session.flush()

    for oi_data in order_items:
        p = oi_data["product"]
        oi = OrderItem(
            order_id=order.id,
            product_id=p.id,
            product_name=p.name,
            quantity=oi_data["qty"],
            unit_price=oi_data["price"],
            total_price=round(oi_data["price"] * oi_data["qty"], 2),
        )
        p.stock -= oi_data["qty"]
        db.session.add(oi)

    db.session.commit()
    return _ok({"order_number": order_number, "order_id": order.id, "total": total}, status=201)


@store_bp.route("/api/store/categories", methods=["GET"])
def api_categories():
    from ecommerce.models import Category
    cats = Category.query.order_by(Category.name).all()
    return _ok([c.to_dict() for c in cats])


@store_bp.route("/api/store/sync/pull-all", methods=["POST"])
def api_sync_pull_all():
    """Pull products from all connected stores into local DB."""
    results: dict = {}

    from core.config import config
    if config.SHOPIFY_ACCESS_TOKEN:
        try:
            from ecommerce.shopify.sync import pull_products
            results["shopify"] = pull_products()
        except Exception as e:
            results["shopify"] = {"error": str(e)}

    if config.SALLA_ACCESS_TOKEN:
        try:
            from ecommerce.salla.routes import sync_pull
            with store_bp.open_resource:
                pass
        except Exception:
            pass
        try:
            from ecommerce.salla.client import get_client as salla_c
            from ecommerce.models import db, Product
            from core.app import app
            created = updated = 0
            with app.app_context():
                resp = salla_c().list_products(per_page=100)
                for sp in resp.get("data", []):
                    sku = f"salla:{sp.get('sku') or sp.get('id', '')}"
                    existing = Product.query.filter_by(sku=sku).first()
                    price_field = sp.get("price", {})
                    price = float(price_field.get("amount", 0) if isinstance(price_field, dict) else price_field)
                    if existing:
                        existing.price = price
                        updated += 1
                    else:
                        db.session.add(Product(
                            name=sp.get("name", ""), price=price,
                            stock=int(sp.get("quantity", 0)), sku=sku,
                        ))
                        created += 1
                db.session.commit()
            results["salla"] = {"created": created, "updated": updated}
        except Exception as e:
            results["salla"] = {"error": str(e)}

    if config.ZID_ACCESS_TOKEN:
        try:
            from ecommerce.zid.client import get_client as zid_c
            from ecommerce.models import db, Product
            from core.app import app
            created = updated = 0
            with app.app_context():
                resp = zid_c().list_products(per_page=100)
                for zp in resp.get("products", []):
                    sku = f"zid:{zp.get('sku') or zp.get('id', '')}"
                    existing = Product.query.filter_by(sku=sku).first()
                    name_f = zp.get("name", {})
                    name = name_f.get("ar") or name_f.get("en") or "" if isinstance(name_f, dict) else str(name_f)
                    price = float(zp.get("price", 0))
                    if existing:
                        existing.price = price
                        updated += 1
                    else:
                        db.session.add(Product(name=name, price=price,
                                               stock=int(zp.get("quantity", 0)), sku=sku))
                        created += 1
                db.session.commit()
            results["zid"] = {"created": created, "updated": updated}
        except Exception as e:
            results["zid"] = {"error": str(e)}

    return _ok(results)
