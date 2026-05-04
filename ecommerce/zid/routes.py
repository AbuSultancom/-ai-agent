"""Zid integration endpoints — /api/zid"""
from __future__ import annotations
import logging
from flask import Blueprint, jsonify, request
from ecommerce.zid.client import ZidError, get_client

logger = logging.getLogger(__name__)
zid_bp = Blueprint("zid", __name__, url_prefix="/api/zid")


def _ok(data=None, status: int = 200, **extra):
    p = {"success": True}
    if data is not None:
        p["data"] = data
    p.update(extra)
    return jsonify(p), status


def _err(msg: str, status: int = 400):
    return jsonify({"success": False, "error": msg}), status


@zid_bp.route("/status", methods=["GET"])
def status():
    try:
        store = get_client().get_store().get("store", {})
        return _ok({"connected": True, "store": store.get("name"), "domain": store.get("subdomain")})
    except ZidError as e:
        return _ok({"connected": False, "error": str(e)})


@zid_bp.route("/products", methods=["GET"])
def list_products():
    try:
        result = get_client().list_products(
            page=int(request.args.get("page", 1)),
            per_page=min(int(request.args.get("per_page", 50)), 100),
            search=request.args.get("search", ""),
        )
        return _ok(result.get("products", []), total=result.get("total", 0))
    except ZidError as e:
        return _err(str(e), e.status_code or 400)


@zid_bp.route("/products/<product_id>", methods=["GET"])
def get_product(product_id: str):
    try:
        return _ok(get_client().get_product(product_id).get("product"))
    except ZidError as e:
        return _err(str(e), e.status_code or 400)


@zid_bp.route("/products", methods=["POST"])
def create_product():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    price = body.get("price")
    if not name or price is None:
        return _err("name and price are required")
    try:
        result = get_client().create_product(
            name=name, price=float(price),
            description=body.get("description", ""),
            quantity=int(body.get("quantity", 0)),
            sku=body.get("sku", ""),
        )
        return _ok(result.get("product"), status=201)
    except ZidError as e:
        return _err(str(e), e.status_code or 400)


@zid_bp.route("/orders", methods=["GET"])
def list_orders():
    try:
        result = get_client().list_orders(
            page=int(request.args.get("page", 1)),
            per_page=min(int(request.args.get("per_page", 50)), 100),
            status=request.args.get("status", ""),
        )
        return _ok(result.get("orders", []))
    except ZidError as e:
        return _err(str(e), e.status_code or 400)


@zid_bp.route("/orders/<order_id>", methods=["GET"])
def get_order(order_id: str):
    try:
        return _ok(get_client().get_order(order_id).get("order"))
    except ZidError as e:
        return _err(str(e), e.status_code or 400)


@zid_bp.route("/customers", methods=["GET"])
def list_customers():
    try:
        result = get_client().list_customers(
            page=int(request.args.get("page", 1)),
            per_page=min(int(request.args.get("per_page", 50)), 100),
        )
        return _ok(result.get("customers", []))
    except ZidError as e:
        return _err(str(e), e.status_code or 400)


@zid_bp.route("/sync/pull", methods=["POST"])
def sync_pull():
    """Import Zid products into local DB."""
    from ecommerce.models import db, Product
    from core.app import app
    client = get_client()
    created = updated = 0
    try:
        with app.app_context():
            resp = client.list_products(per_page=100)
            for zp in resp.get("products", []):
                sku = zp.get("sku") or str(zp.get("id", ""))
                name_field = zp.get("name", {})
                name = name_field.get("ar") or name_field.get("en") or str(name_field) if isinstance(name_field, dict) else str(name_field)
                price = float(zp.get("price", 0))
                existing = Product.query.filter_by(sku=f"zid:{sku}").first()
                imgs = zp.get("images") or []
                image_url = imgs[0].get("url", "") if imgs else ""
                if existing:
                    existing.name = name
                    existing.price = price
                    existing.stock = int(zp.get("quantity", existing.stock))
                    updated += 1
                else:
                    p = Product(
                        name=name,
                        description="",
                        price=price,
                        stock=int(zp.get("quantity", 0)),
                        sku=f"zid:{sku}",
                        image_url=image_url,
                    )
                    db.session.add(p)
                    created += 1
            db.session.commit()
        return _ok({"products": {"created": created, "updated": updated}})
    except ZidError as e:
        return _err(str(e), e.status_code or 400)
