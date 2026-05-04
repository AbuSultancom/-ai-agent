"""
E-commerce REST API blueprint.

Endpoints:
  Categories : GET/POST /api/ecommerce/categories
               GET/PUT/DELETE /api/ecommerce/categories/<id>
  Products   : GET/POST /api/ecommerce/products
               GET/PUT/DELETE /api/ecommerce/products/<id>
  Customers  : GET/POST /api/ecommerce/customers
               GET/PUT/DELETE /api/ecommerce/customers/<id>
  Cart       : GET/POST /api/ecommerce/cart
               PUT/DELETE /api/ecommerce/cart/<id>/item
               DELETE /api/ecommerce/cart/<id>
  Orders     : GET/POST /api/ecommerce/orders
               GET/PUT /api/ecommerce/orders/<id>
  Checkout   : POST /api/ecommerce/checkout
  AI         : POST /api/ecommerce/ai/recommend
               POST /api/ecommerce/ai/analyze-order
               GET  /api/ecommerce/ai/insights
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from ecommerce.models import (
    Cart,
    Category,
    Customer,
    Order,
    OrderItem,
    OrderStatus,
    Product,
    db,
)

logger = logging.getLogger(__name__)

ecommerce_bp = Blueprint("ecommerce", __name__, url_prefix="/api/ecommerce")


# ─── helpers ──────────────────────────────────────────────────────────────────

def _ok(data=None, status: int = 200, **extra):
    payload = {"success": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return jsonify(payload), status


def _err(message: str, status: int = 400):
    return jsonify({"success": False, "error": message}), status


def _generate_order_number() -> str:
    from random import randint
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"ORD-{ts}-{randint(100, 999)}"


# ─── categories ───────────────────────────────────────────────────────────────

@ecommerce_bp.route("/categories", methods=["GET"])
def list_categories():
    cats = Category.query.order_by(Category.name).all()
    return _ok([c.to_dict() for c in cats], total=len(cats))


@ecommerce_bp.route("/categories", methods=["POST"])
def create_category():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return _err("name is required")
    if Category.query.filter_by(name=name).first():
        return _err(f"Category '{name}' already exists", 409)
    cat = Category(name=name, description=body.get("description", ""))
    db.session.add(cat)
    db.session.commit()
    return _ok(cat.to_dict(), status=201)


@ecommerce_bp.route("/categories/<cat_id>", methods=["GET"])
def get_category(cat_id: str):
    cat = Category.query.get_or_404(cat_id)
    return _ok(cat.to_dict())


@ecommerce_bp.route("/categories/<cat_id>", methods=["PUT"])
def update_category(cat_id: str):
    cat = Category.query.get_or_404(cat_id)
    body = request.get_json(silent=True) or {}
    if "name" in body:
        cat.name = body["name"].strip()
    if "description" in body:
        cat.description = body["description"]
    db.session.commit()
    return _ok(cat.to_dict())


@ecommerce_bp.route("/categories/<cat_id>", methods=["DELETE"])
def delete_category(cat_id: str):
    cat = Category.query.get_or_404(cat_id)
    db.session.delete(cat)
    db.session.commit()
    return _ok({"deleted": cat_id})


# ─── products ─────────────────────────────────────────────────────────────────

@ecommerce_bp.route("/products", methods=["GET"])
def list_products():
    q = Product.query
    category_id = request.args.get("category_id")
    search = request.args.get("search")
    min_price = request.args.get("min_price", type=float)
    max_price = request.args.get("max_price", type=float)
    in_stock = request.args.get("in_stock")
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)

    if category_id:
        q = q.filter_by(category_id=category_id)
    if search:
        q = q.filter(Product.name.ilike(f"%{search}%") | Product.description.ilike(f"%{search}%"))
    if min_price is not None:
        q = q.filter(Product.price >= min_price)
    if max_price is not None:
        q = q.filter(Product.price <= max_price)
    if in_stock and in_stock.lower() == "true":
        q = q.filter(Product.stock > 0)
    q = q.filter_by(is_active=True)

    pagination = q.order_by(Product.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return _ok(
        [p.to_dict() for p in pagination.items],
        total=pagination.total,
        page=page,
        per_page=per_page,
        pages=pagination.pages,
    )


@ecommerce_bp.route("/products", methods=["POST"])
def create_product():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    price = body.get("price")
    if not name:
        return _err("name is required")
    if price is None or float(price) < 0:
        return _err("valid price is required")

    product = Product(
        name=name,
        description=body.get("description", ""),
        price=float(price),
        stock=int(body.get("stock", 0)),
        category_id=body.get("category_id"),
        image_url=body.get("image_url", ""),
        sku=body.get("sku"),
        is_active=body.get("is_active", True),
    )
    db.session.add(product)
    db.session.commit()
    return _ok(product.to_dict(), status=201)


@ecommerce_bp.route("/products/<product_id>", methods=["GET"])
def get_product(product_id: str):
    product = Product.query.get_or_404(product_id)
    return _ok(product.to_dict())


@ecommerce_bp.route("/products/<product_id>", methods=["PUT"])
def update_product(product_id: str):
    product = Product.query.get_or_404(product_id)
    body = request.get_json(silent=True) or {}
    for field in ("name", "description", "image_url", "sku"):
        if field in body:
            setattr(product, field, body[field])
    if "price" in body:
        product.price = float(body["price"])
    if "stock" in body:
        product.stock = int(body["stock"])
    if "category_id" in body:
        product.category_id = body["category_id"]
    if "is_active" in body:
        product.is_active = bool(body["is_active"])
    product.updated_at = datetime.utcnow()
    db.session.commit()
    return _ok(product.to_dict())


@ecommerce_bp.route("/products/<product_id>", methods=["DELETE"])
def delete_product(product_id: str):
    product = Product.query.get_or_404(product_id)
    product.is_active = False
    db.session.commit()
    return _ok({"deleted": product_id})


# ─── customers ────────────────────────────────────────────────────────────────

@ecommerce_bp.route("/customers", methods=["GET"])
def list_customers():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    search = request.args.get("search")
    q = Customer.query
    if search:
        q = q.filter(Customer.name.ilike(f"%{search}%") | Customer.email.ilike(f"%{search}%"))
    pagination = q.order_by(Customer.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return _ok([c.to_dict() for c in pagination.items], total=pagination.total, page=page, pages=pagination.pages)


@ecommerce_bp.route("/customers", methods=["POST"])
def create_customer():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    email = (body.get("email") or "").strip().lower()
    if not name or not email:
        return _err("name and email are required")
    if Customer.query.filter_by(email=email).first():
        return _err(f"Customer with email '{email}' already exists", 409)
    customer = Customer(
        name=name,
        email=email,
        phone=body.get("phone", ""),
        address=body.get("address", ""),
        city=body.get("city", ""),
        country=body.get("country", ""),
    )
    db.session.add(customer)
    db.session.commit()
    return _ok(customer.to_dict(), status=201)


@ecommerce_bp.route("/customers/<customer_id>", methods=["GET"])
def get_customer(customer_id: str):
    customer = Customer.query.get_or_404(customer_id)
    return _ok(customer.to_dict())


@ecommerce_bp.route("/customers/<customer_id>", methods=["PUT"])
def update_customer(customer_id: str):
    customer = Customer.query.get_or_404(customer_id)
    body = request.get_json(silent=True) or {}
    for field in ("name", "phone", "address", "city", "country"):
        if field in body:
            setattr(customer, field, body[field])
    if "email" in body:
        customer.email = body["email"].strip().lower()
    db.session.commit()
    return _ok(customer.to_dict())


@ecommerce_bp.route("/customers/<customer_id>", methods=["DELETE"])
def delete_customer(customer_id: str):
    customer = Customer.query.get_or_404(customer_id)
    db.session.delete(customer)
    db.session.commit()
    return _ok({"deleted": customer_id})


# ─── cart ─────────────────────────────────────────────────────────────────────

@ecommerce_bp.route("/cart", methods=["POST"])
def create_or_get_cart():
    """Create a new cart or return existing one by session_id / customer_id."""
    body = request.get_json(silent=True) or {}
    customer_id = body.get("customer_id")
    session_id = body.get("session_id")

    if not customer_id and not session_id:
        return _err("customer_id or session_id is required")

    cart = None
    if customer_id:
        cart = Cart.query.filter_by(customer_id=customer_id).order_by(Cart.created_at.desc()).first()
    elif session_id:
        cart = Cart.query.filter_by(session_id=session_id).first()

    if not cart:
        cart = Cart(customer_id=customer_id, session_id=session_id)
        db.session.add(cart)
        db.session.commit()

    return _ok(cart.to_dict())


@ecommerce_bp.route("/cart/<cart_id>", methods=["GET"])
def get_cart(cart_id: str):
    cart = Cart.query.get_or_404(cart_id)
    return _ok(cart.to_dict())


@ecommerce_bp.route("/cart/<cart_id>/item", methods=["POST"])
def add_to_cart(cart_id: str):
    cart = Cart.query.get_or_404(cart_id)
    body = request.get_json(silent=True) or {}
    product_id = body.get("product_id")
    quantity = int(body.get("quantity", 1))

    if not product_id:
        return _err("product_id is required")
    if quantity < 1:
        return _err("quantity must be at least 1")

    product = Product.query.get_or_404(product_id)
    if not product.is_active:
        return _err("Product is not available")
    if product.stock < quantity:
        return _err(f"Only {product.stock} units available in stock")

    cart.add_item(product_id, quantity, product.price, product.name)
    cart.updated_at = datetime.utcnow()
    db.session.commit()
    return _ok(cart.to_dict())


@ecommerce_bp.route("/cart/<cart_id>/item/<product_id>", methods=["PUT"])
def update_cart_item(cart_id: str, product_id: str):
    cart = Cart.query.get_or_404(cart_id)
    body = request.get_json(silent=True) or {}
    quantity = body.get("quantity")
    if quantity is None:
        return _err("quantity is required")
    if not cart.update_quantity(product_id, int(quantity)):
        return _err("Item not found in cart", 404)
    cart.updated_at = datetime.utcnow()
    db.session.commit()
    return _ok(cart.to_dict())


@ecommerce_bp.route("/cart/<cart_id>/item/<product_id>", methods=["DELETE"])
def remove_from_cart(cart_id: str, product_id: str):
    cart = Cart.query.get_or_404(cart_id)
    if not cart.remove_item(product_id):
        return _err("Item not found in cart", 404)
    cart.updated_at = datetime.utcnow()
    db.session.commit()
    return _ok(cart.to_dict())


@ecommerce_bp.route("/cart/<cart_id>", methods=["DELETE"])
def clear_cart(cart_id: str):
    cart = Cart.query.get_or_404(cart_id)
    cart.items = []
    cart.updated_at = datetime.utcnow()
    db.session.commit()
    return _ok({"cleared": cart_id})


# ─── checkout ─────────────────────────────────────────────────────────────────

@ecommerce_bp.route("/checkout", methods=["POST"])
def checkout():
    """Convert a cart into an order."""
    body = request.get_json(silent=True) or {}
    cart_id = body.get("cart_id")
    customer_id = body.get("customer_id")
    shipping_address = body.get("shipping_address", "")
    notes = body.get("notes", "")
    shipping_cost = float(body.get("shipping_cost", 0.0))
    tax_rate = float(body.get("tax_rate", 0.15))  # 15% default VAT

    if not cart_id:
        return _err("cart_id is required")

    cart = Cart.query.get_or_404(cart_id)
    if not cart.items:
        return _err("Cart is empty")

    # validate stock
    for item in cart.items:
        product = Product.query.get(item["product_id"])
        if not product or not product.is_active:
            return _err(f"Product '{item['name']}' is no longer available")
        if product.stock < item["quantity"]:
            return _err(f"Insufficient stock for '{item['name']}': only {product.stock} left")

    subtotal = round(cart.total, 2)
    tax = round(subtotal * tax_rate, 2)
    total = round(subtotal + tax + shipping_cost, 2)

    order = Order(
        order_number=_generate_order_number(),
        customer_id=customer_id or cart.customer_id,
        status=OrderStatus.CONFIRMED.value,
        subtotal=subtotal,
        tax=tax,
        shipping=shipping_cost,
        total=total,
        shipping_address=shipping_address,
        notes=notes,
    )
    db.session.add(order)
    db.session.flush()

    for item in cart.items:
        product = Product.query.get(item["product_id"])
        oi = OrderItem(
            order_id=order.id,
            product_id=item["product_id"],
            product_name=item["name"],
            quantity=item["quantity"],
            unit_price=item["price"],
            total_price=round(item["price"] * item["quantity"], 2),
        )
        product.stock -= item["quantity"]
        db.session.add(oi)

    # clear cart after checkout
    cart.items = []
    cart.updated_at = datetime.utcnow()
    db.session.commit()

    return _ok(order.to_dict(), status=201)


# ─── orders ───────────────────────────────────────────────────────────────────

@ecommerce_bp.route("/orders", methods=["GET"])
def list_orders():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    status = request.args.get("status")
    customer_id = request.args.get("customer_id")

    q = Order.query
    if status:
        q = q.filter_by(status=status)
    if customer_id:
        q = q.filter_by(customer_id=customer_id)

    pagination = q.order_by(Order.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return _ok(
        [o.to_dict(include_items=False) for o in pagination.items],
        total=pagination.total,
        page=page,
        pages=pagination.pages,
    )


@ecommerce_bp.route("/orders/<order_id>", methods=["GET"])
def get_order(order_id: str):
    order = Order.query.get_or_404(order_id)
    return _ok(order.to_dict())


@ecommerce_bp.route("/orders/<order_id>/status", methods=["PUT"])
def update_order_status(order_id: str):
    order = Order.query.get_or_404(order_id)
    body = request.get_json(silent=True) or {}
    new_status = body.get("status")
    valid = [s.value for s in OrderStatus]
    if new_status not in valid:
        return _err(f"Invalid status. Choose from: {valid}")
    order.status = new_status
    order.updated_at = datetime.utcnow()
    db.session.commit()
    return _ok(order.to_dict())


# ─── AI features ──────────────────────────────────────────────────────────────

@ecommerce_bp.route("/ai/recommend", methods=["POST"])
def ai_recommend():
    """Use Claude to recommend products based on customer history or description."""
    body = request.get_json(silent=True) or {}
    customer_id = body.get("customer_id")
    query = body.get("query", "")
    limit = int(body.get("limit", 5))

    context_parts = []

    # build context from customer's order history
    if customer_id:
        customer = Customer.query.get(customer_id)
        if customer:
            past_orders = customer.orders.order_by(Order.created_at.desc()).limit(5).all()
            purchased = []
            for order in past_orders:
                for item in order.items:
                    purchased.append(f"{item.product_name} (qty: {item.quantity})")
            if purchased:
                context_parts.append(f"Customer previously bought: {', '.join(purchased)}")

    # get available products for context
    products = Product.query.filter_by(is_active=True).filter(Product.stock > 0).limit(50).all()
    product_list = [f"- {p.name}: ${p.price:.2f} (stock: {p.stock})" for p in products]
    context_parts.append("Available products:\n" + "\n".join(product_list))

    if query:
        context_parts.append(f"Customer request: {query}")

    prompt = "\n\n".join(context_parts) + f"\n\nRecommend the top {limit} products from the list above. Return as JSON array with product names and brief reasons."

    try:
        from core.config import config
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=config.MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        recommendation_text = response.content[0].text
        return _ok({"recommendations": recommendation_text, "product_count": len(products)})
    except Exception as e:
        logger.error("AI recommendation failed: %s", e)
        # fallback: return top products by stock
        top = products[:limit]
        return _ok({"recommendations": [p.to_dict() for p in top], "note": "AI unavailable, showing top products"})


@ecommerce_bp.route("/ai/analyze-order", methods=["POST"])
def ai_analyze_order():
    """Use Claude to analyze an order and generate fulfillment notes."""
    body = request.get_json(silent=True) or {}
    order_id = body.get("order_id")
    if not order_id:
        return _err("order_id is required")

    order = Order.query.get_or_404(order_id)
    order_summary = order.to_dict()

    prompt = f"""Analyze this e-commerce order and provide:
1. Priority level (low/medium/high/urgent)
2. Fulfillment recommendations
3. Any red flags or special notes
4. Estimated processing time

Order: {order_summary}
"""

    try:
        from core.config import config
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=config.MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        analysis = response.content[0].text
        return _ok({"order_id": order_id, "analysis": analysis})
    except Exception as e:
        logger.error("Order analysis failed: %s", e)
        return _err(f"AI analysis unavailable: {e}", 503)


@ecommerce_bp.route("/ai/insights", methods=["GET"])
def ai_insights():
    """Generate AI-powered business insights from store data."""
    total_products = Product.query.filter_by(is_active=True).count()
    total_customers = Customer.query.count()
    total_orders = Order.query.count()
    total_revenue = db.session.query(db.func.sum(Order.total)).scalar() or 0
    pending_orders = Order.query.filter_by(status=OrderStatus.PENDING.value).count()
    low_stock = Product.query.filter(Product.stock <= 5, Product.is_active == True).count()

    stats = {
        "total_products": total_products,
        "total_customers": total_customers,
        "total_orders": total_orders,
        "total_revenue": round(float(total_revenue), 2),
        "pending_orders": pending_orders,
        "low_stock_products": low_stock,
    }

    prompt = f"""You are an e-commerce business analyst. Based on these store metrics, provide actionable business insights in Arabic and English:

{stats}

Provide:
1. Key observations (ملاحظات رئيسية)
2. Opportunities (فرص)
3. Risks (مخاطر)
4. Recommended actions (إجراءات موصى بها)
"""

    try:
        from core.config import config
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=config.MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        insights = response.content[0].text
        return _ok({"stats": stats, "insights": insights})
    except Exception as e:
        logger.error("Insights generation failed: %s", e)
        return _ok({"stats": stats, "insights": None, "note": "AI unavailable"})


# ─── dashboard stats ──────────────────────────────────────────────────────────

@ecommerce_bp.route("/dashboard", methods=["GET"])
def dashboard():
    """Quick summary of store health."""
    total_revenue = db.session.query(db.func.sum(Order.total)).scalar() or 0
    orders_by_status = {}
    for status in OrderStatus:
        count = Order.query.filter_by(status=status.value).count()
        if count:
            orders_by_status[status.value] = count

    return _ok({
        "products": {
            "total": Product.query.filter_by(is_active=True).count(),
            "low_stock": Product.query.filter(Product.stock <= 5, Product.is_active == True).count(),
            "out_of_stock": Product.query.filter(Product.stock == 0, Product.is_active == True).count(),
        },
        "customers": {
            "total": Customer.query.count(),
        },
        "orders": {
            "total": Order.query.count(),
            "by_status": orders_by_status,
        },
        "revenue": {
            "total": round(float(total_revenue), 2),
        },
    })
