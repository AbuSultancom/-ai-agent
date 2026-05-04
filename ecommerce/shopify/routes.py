"""
Shopify integration Flask blueprint.

Base path: /api/shopify

Store management:
  GET  /api/shopify/shop                   Store info
  GET  /api/shopify/status                 Connection status + counts

Products:
  GET  /api/shopify/products               List Shopify products
  POST /api/shopify/products               Create product on Shopify
  GET  /api/shopify/products/<id>          Get single product
  PUT  /api/shopify/products/<id>          Update product
  DELETE /api/shopify/products/<id>        Delete product
  GET  /api/shopify/products/count         Product count

Inventory:
  GET  /api/shopify/inventory              List inventory levels
  PUT  /api/shopify/inventory              Set inventory level
  GET  /api/shopify/locations              List locations

Customers:
  GET  /api/shopify/customers              List customers
  POST /api/shopify/customers              Create customer
  GET  /api/shopify/customers/<id>         Get customer

Orders:
  GET  /api/shopify/orders                 List orders
  GET  /api/shopify/orders/<id>            Get order
  PUT  /api/shopify/orders/<id>/cancel     Cancel order
  POST /api/shopify/orders/<id>/fulfill    Fulfill order

Discounts:
  GET  /api/shopify/price-rules            List price rules
  POST /api/shopify/price-rules            Create price rule + discount code

Webhooks:
  GET  /api/shopify/webhooks               List registered webhooks
  POST /api/shopify/webhooks               Register a webhook
  DELETE /api/shopify/webhooks/<id>        Remove webhook
  POST /api/shopify/webhooks/register-all  Auto-register all supported topics
  POST /api/shopify/webhooks/receive       Incoming Shopify webhook (HMAC verified)

Sync:
  POST /api/shopify/sync/pull              Full pull: Shopify → local DB
  POST /api/shopify/sync/pull/products     Pull products only
  POST /api/shopify/sync/pull/customers    Pull customers only
  POST /api/shopify/sync/pull/orders       Pull orders only
  POST /api/shopify/sync/push/products     Push local products → Shopify
  POST /api/shopify/sync/push/product/<id> Push single product → Shopify

AI:
  POST /api/shopify/ai/product-description Generate SEO product description
  POST /api/shopify/ai/pricing-strategy    AI pricing recommendations
  GET  /api/shopify/ai/store-insights      AI analysis of store performance
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from ecommerce.shopify.client import ShopifyError, get_client, verify_webhook_signature
from ecommerce.shopify.webhooks import process_webhook

logger = logging.getLogger(__name__)

shopify_bp = Blueprint("shopify", __name__, url_prefix="/api/shopify")


# ── helpers ───────────────────────────────────────────────────────────────────

def _ok(data=None, status: int = 200, **extra):
    payload = {"success": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return jsonify(payload), status


def _err(message: str, status: int = 400):
    return jsonify({"success": False, "error": message}), status


def _client():
    try:
        return get_client()
    except ShopifyError as e:
        return None, str(e)


# ── store info ────────────────────────────────────────────────────────────────

@shopify_bp.route("/shop", methods=["GET"])
def shop_info():
    try:
        client = get_client()
        shop = client.get_shop().get("shop", {})
        return _ok({
            "name": shop.get("name"),
            "domain": shop.get("domain"),
            "email": shop.get("email"),
            "currency": shop.get("currency"),
            "plan": shop.get("plan_name"),
            "country": shop.get("country_name"),
            "timezone": shop.get("iana_timezone"),
        })
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


@shopify_bp.route("/status", methods=["GET"])
def connection_status():
    try:
        client = get_client()
        shop = client.get_shop().get("shop", {})
        product_count = client.count_products()
        customer_count = client.count_customers()
        order_count = client.count_orders()
        return _ok({
            "connected": True,
            "shop": shop.get("name"),
            "domain": shop.get("domain"),
            "currency": shop.get("currency"),
            "products": product_count,
            "customers": customer_count,
            "orders": order_count,
        })
    except ShopifyError as e:
        return _ok({"connected": False, "error": str(e)})


# ── products ──────────────────────────────────────────────────────────────────

@shopify_bp.route("/products", methods=["GET"])
def list_products():
    try:
        client = get_client()
        limit = min(int(request.args.get("limit", 50)), 250)
        status = request.args.get("status", "active")
        result = client.list_products(limit=limit, status=status)
        products = result.get("products", [])
        return _ok(products, total=len(products))
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


@shopify_bp.route("/products/count", methods=["GET"])
def count_products():
    try:
        return _ok({"count": get_client().count_products()})
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


@shopify_bp.route("/products/<int:product_id>", methods=["GET"])
def get_product(product_id: int):
    try:
        result = get_client().get_product(product_id)
        return _ok(result.get("product"))
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


@shopify_bp.route("/products", methods=["POST"])
def create_product():
    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()
    if not title:
        return _err("title is required")
    try:
        result = get_client().create_product(
            title=title,
            body_html=body.get("body_html", body.get("description", "")),
            vendor=body.get("vendor", ""),
            product_type=body.get("product_type", ""),
            tags=body.get("tags", ""),
            variants=body.get("variants"),
            images=body.get("images"),
        )
        return _ok(result.get("product"), status=201)
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


@shopify_bp.route("/products/<int:product_id>", methods=["PUT"])
def update_product(product_id: int):
    body = request.get_json(silent=True) or {}
    if not body:
        return _err("No fields provided")
    try:
        result = get_client().update_product(product_id, **body)
        return _ok(result.get("product"))
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


@shopify_bp.route("/products/<int:product_id>", methods=["DELETE"])
def delete_product(product_id: int):
    try:
        get_client().delete_product(product_id)
        return _ok({"deleted": product_id})
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


# ── inventory ─────────────────────────────────────────────────────────────────

@shopify_bp.route("/locations", methods=["GET"])
def list_locations():
    try:
        result = get_client().list_locations()
        return _ok(result.get("locations", []))
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


@shopify_bp.route("/inventory", methods=["GET"])
def list_inventory():
    try:
        item_ids = request.args.get("inventory_item_ids")
        location_ids = request.args.get("location_ids")
        item_id_list = [int(x) for x in item_ids.split(",")] if item_ids else None
        loc_id_list = [int(x) for x in location_ids.split(",")] if location_ids else None
        result = get_client().list_inventory_levels(item_id_list, loc_id_list)
        return _ok(result.get("inventory_levels", []))
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


@shopify_bp.route("/inventory", methods=["PUT"])
def set_inventory():
    body = request.get_json(silent=True) or {}
    inventory_item_id = body.get("inventory_item_id")
    location_id = body.get("location_id")
    available = body.get("available")
    if None in (inventory_item_id, location_id, available):
        return _err("inventory_item_id, location_id, and available are required")
    try:
        result = get_client().set_inventory_level(
            int(inventory_item_id), int(location_id), int(available)
        )
        return _ok(result.get("inventory_level"))
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


# ── customers ─────────────────────────────────────────────────────────────────

@shopify_bp.route("/customers", methods=["GET"])
def list_customers():
    try:
        limit = min(int(request.args.get("limit", 50)), 250)
        result = get_client().list_customers(limit=limit)
        customers = result.get("customers", [])
        return _ok(customers, total=len(customers))
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


@shopify_bp.route("/customers/<int:customer_id>", methods=["GET"])
def get_customer(customer_id: int):
    try:
        result = get_client().get_customer(customer_id)
        return _ok(result.get("customer"))
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


@shopify_bp.route("/customers", methods=["POST"])
def create_customer():
    body = request.get_json(silent=True) or {}
    first = (body.get("first_name") or "").strip()
    last = (body.get("last_name") or "").strip()
    email = (body.get("email") or "").strip()
    if not email:
        return _err("email is required")
    try:
        result = get_client().create_customer(
            first_name=first, last_name=last, email=email,
            phone=body.get("phone", ""), tags=body.get("tags", ""),
            addresses=body.get("addresses"),
        )
        return _ok(result.get("customer"), status=201)
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


# ── orders ────────────────────────────────────────────────────────────────────

@shopify_bp.route("/orders", methods=["GET"])
def list_orders():
    try:
        limit = min(int(request.args.get("limit", 50)), 250)
        status = request.args.get("status", "any")
        financial = request.args.get("financial_status")
        fulfillment = request.args.get("fulfillment_status")
        result = get_client().list_orders(
            status=status, limit=limit,
            financial_status=financial, fulfillment_status=fulfillment,
        )
        orders = result.get("orders", [])
        return _ok(orders, total=len(orders))
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


@shopify_bp.route("/orders/<int:order_id>", methods=["GET"])
def get_order(order_id: int):
    try:
        result = get_client().get_order(order_id)
        return _ok(result.get("order"))
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


@shopify_bp.route("/orders/<int:order_id>/cancel", methods=["PUT"])
def cancel_order(order_id: int):
    body = request.get_json(silent=True) or {}
    try:
        result = get_client().cancel_order(
            order_id,
            reason=body.get("reason", "other"),
            email=body.get("notify_customer", True),
        )
        return _ok(result.get("order"))
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


@shopify_bp.route("/orders/<int:order_id>/fulfill", methods=["POST"])
def fulfill_order(order_id: int):
    body = request.get_json(silent=True) or {}
    location_id = body.get("location_id")
    if not location_id:
        # use first available location
        try:
            locs = get_client().list_locations().get("locations", [])
            if not locs:
                return _err("No locations found on Shopify store")
            location_id = locs[0]["id"]
        except ShopifyError as e:
            return _err(str(e), e.status_code or 400)
    try:
        result = get_client().create_fulfillment(
            order_id=order_id,
            location_id=int(location_id),
            tracking_number=body.get("tracking_number", ""),
            tracking_company=body.get("tracking_company", ""),
            notify_customer=body.get("notify_customer", True),
        )
        return _ok(result.get("fulfillment"), status=201)
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


# ── discounts ─────────────────────────────────────────────────────────────────

@shopify_bp.route("/price-rules", methods=["GET"])
def list_price_rules():
    try:
        result = get_client().list_price_rules()
        return _ok(result.get("price_rules", []))
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


@shopify_bp.route("/price-rules", methods=["POST"])
def create_price_rule():
    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()
    value = body.get("value")
    code = (body.get("code") or "").strip()
    if not title or value is None:
        return _err("title and value are required")
    try:
        client = get_client()
        rule_result = client.create_price_rule(
            title=title,
            value=float(value),
            value_type=body.get("value_type", "percentage"),
            starts_at=body.get("starts_at"),
        )
        price_rule = rule_result.get("price_rule", {})
        discount_code = None
        if code and price_rule.get("id"):
            dc_result = client.create_discount_code(price_rule["id"], code)
            discount_code = dc_result.get("discount_code", {}).get("code")
        return _ok({"price_rule": price_rule, "discount_code": discount_code}, status=201)
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


# ── webhooks ──────────────────────────────────────────────────────────────────

_SUPPORTED_TOPICS = [
    "orders/created", "orders/updated", "orders/cancelled", "orders/fulfilled",
    "products/create", "products/update", "products/delete",
    "inventory_levels/update",
    "customers/create", "customers/update",
    "app/uninstalled",
]


@shopify_bp.route("/webhooks", methods=["GET"])
def list_webhooks():
    try:
        result = get_client().list_webhooks()
        return _ok(result.get("webhooks", []))
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


@shopify_bp.route("/webhooks", methods=["POST"])
def create_webhook():
    body = request.get_json(silent=True) or {}
    topic = (body.get("topic") or "").strip()
    address = (body.get("address") or "").strip()
    if not topic or not address:
        return _err("topic and address are required")
    if topic not in _SUPPORTED_TOPICS:
        return _err(f"Unsupported topic. Supported: {_SUPPORTED_TOPICS}")
    try:
        result = get_client().create_webhook(topic=topic, address=address)
        return _ok(result.get("webhook"), status=201)
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


@shopify_bp.route("/webhooks/<int:webhook_id>", methods=["DELETE"])
def delete_webhook(webhook_id: int):
    try:
        get_client().delete_webhook(webhook_id)
        return _ok({"deleted": webhook_id})
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


@shopify_bp.route("/webhooks/register-all", methods=["POST"])
def register_all_webhooks():
    """Register all supported webhook topics pointing to this server."""
    body = request.get_json(silent=True) or {}
    base_url = (body.get("base_url") or "").rstrip("/")
    if not base_url:
        return _err("base_url is required (e.g. https://your-server.com)")

    receive_url = f"{base_url}/api/shopify/webhooks/receive"
    client = get_client()
    registered = []
    errors = []

    # delete existing webhooks to avoid duplicates
    try:
        existing = client.list_webhooks().get("webhooks", [])
        for wh in existing:
            if wh.get("address") == receive_url:
                client.delete_webhook(wh["id"])
    except ShopifyError:
        pass

    for topic in _SUPPORTED_TOPICS:
        try:
            result = client.create_webhook(topic=topic, address=receive_url)
            registered.append(result.get("webhook", {}).get("topic", topic))
        except ShopifyError as e:
            errors.append({"topic": topic, "error": str(e)})

    return _ok({"registered": registered, "errors": errors, "receive_url": receive_url})


@shopify_bp.route("/webhooks/receive", methods=["POST"])
def receive_webhook():
    """Endpoint Shopify calls when events occur. Verifies HMAC signature."""
    from core.config import config

    raw_body = request.get_data()
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256", "")
    topic = request.headers.get("X-Shopify-Topic", "")
    shop_domain = request.headers.get("X-Shopify-Shop-Domain", "")

    if config.SHOPIFY_WEBHOOK_SECRET:
        if not verify_webhook_signature(raw_body, hmac_header, config.SHOPIFY_WEBHOOK_SECRET):
            logger.warning("Invalid Shopify webhook signature from %s", shop_domain)
            return jsonify({"error": "Invalid signature"}), 401

    try:
        import json
        payload = json.loads(raw_body)
    except Exception:
        return jsonify({"error": "Invalid JSON body"}), 400

    logger.info("Shopify webhook received: topic=%s shop=%s", topic, shop_domain)
    result = process_webhook(topic, payload)
    return jsonify(result), 200


# ── sync ──────────────────────────────────────────────────────────────────────

@shopify_bp.route("/sync/pull", methods=["POST"])
def sync_pull_all():
    try:
        from ecommerce.shopify.sync import pull_all
        result = pull_all()
        return _ok(result)
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)
    except Exception as e:
        logger.exception("Sync pull failed")
        return _err(str(e), 500)


@shopify_bp.route("/sync/pull/products", methods=["POST"])
def sync_pull_products():
    try:
        from ecommerce.shopify.sync import pull_products
        return _ok(pull_products())
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


@shopify_bp.route("/sync/pull/customers", methods=["POST"])
def sync_pull_customers():
    try:
        from ecommerce.shopify.sync import pull_customers
        return _ok(pull_customers())
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


@shopify_bp.route("/sync/pull/orders", methods=["POST"])
def sync_pull_orders():
    body = request.get_json(silent=True) or {}
    try:
        from ecommerce.shopify.sync import pull_orders
        return _ok(pull_orders(status=body.get("status", "any")))
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


@shopify_bp.route("/sync/push/products", methods=["POST"])
def sync_push_all_products():
    try:
        from ecommerce.shopify.sync import push_all_products
        return _ok(push_all_products())
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


@shopify_bp.route("/sync/push/product/<product_id>", methods=["POST"])
def sync_push_product(product_id: str):
    try:
        from ecommerce.shopify.sync import push_product
        return _ok(push_product(product_id))
    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)


# ── AI features ───────────────────────────────────────────────────────────────

@shopify_bp.route("/ai/product-description", methods=["POST"])
def ai_product_description():
    """Generate an SEO-optimized product description using Claude."""
    body = request.get_json(silent=True) or {}
    product_name = (body.get("product_name") or "").strip()
    keywords = body.get("keywords", "")
    tone = body.get("tone", "professional")
    language = body.get("language", "ar")  # default Arabic

    if not product_name:
        return _err("product_name is required")

    lang_instruction = "in Arabic (العربية)" if language == "ar" else f"in {language}"
    prompt = f"""Write a compelling, SEO-optimized product description {lang_instruction} for:

Product: {product_name}
Keywords to include: {keywords}
Tone: {tone}

Requirements:
- 2-3 paragraphs
- Highlight key benefits
- Include a call to action
- Suitable for Shopify product page
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
        return _ok({"description": response.content[0].text, "product_name": product_name})
    except Exception as e:
        return _err(f"AI service error: {e}", 503)


@shopify_bp.route("/ai/pricing-strategy", methods=["POST"])
def ai_pricing_strategy():
    """Get AI-powered pricing recommendations for a product."""
    body = request.get_json(silent=True) or {}
    product_name = (body.get("product_name") or "").strip()
    current_price = body.get("current_price")
    cost = body.get("cost")
    category = body.get("category", "")
    competitors = body.get("competitors", [])

    if not product_name:
        return _err("product_name is required")

    prompt = f"""As an e-commerce pricing strategist, analyze and recommend a pricing strategy:

Product: {product_name}
Category: {category}
Current Price: {current_price} SAR
Cost: {cost} SAR
Competitor prices: {competitors}

Provide in Arabic and English:
1. Optimal price point and justification
2. Pricing strategy (premium / competitive / economy)
3. Discount and promotion recommendations
4. Expected profit margin analysis
"""
    try:
        from core.config import config
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=config.MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        return _ok({"strategy": response.content[0].text})
    except Exception as e:
        return _err(f"AI service error: {e}", 503)


@shopify_bp.route("/ai/store-insights", methods=["GET"])
def ai_store_insights():
    """Pull live Shopify data and generate AI business insights."""
    try:
        client = get_client()
        product_count = client.count_products()
        customer_count = client.count_customers()
        total_orders = client.count_orders(status="any")
        open_orders = client.count_orders(status="open")
        unfulfilled = client.count_orders(status="any") - client.count_orders(status="closed")

        recent_orders = client.list_orders(status="any", limit=10).get("orders", [])
        revenue_sample = sum(float(o.get("total_price", 0)) for o in recent_orders)

        stats = {
            "products": product_count,
            "customers": customer_count,
            "total_orders": total_orders,
            "open_orders": open_orders,
            "recent_revenue_sample": round(revenue_sample, 2),
        }

        from core.config import config
        import anthropic
        ai_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        prompt = f"""Analyze this Shopify store's performance and provide strategic insights in Arabic and English:

Store Metrics:
{stats}

Provide:
1. ملخص الأداء (Performance Summary)
2. نقاط القوة (Strengths)
3. فرص النمو (Growth Opportunities)
4. توصيات فورية (Immediate Recommendations)
5. مؤشرات المراقبة (KPIs to watch)
"""
        response = ai_client.messages.create(
            model=config.MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        return _ok({"stats": stats, "insights": response.content[0].text})

    except ShopifyError as e:
        return _err(str(e), e.status_code or 400)
    except Exception as e:
        logger.exception("Store insights failed")
        return _err(str(e), 500)
