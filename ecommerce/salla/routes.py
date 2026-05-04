"""Salla integration endpoints — /api/salla"""
from __future__ import annotations
import logging
from flask import Blueprint, jsonify, request
from ecommerce.salla.client import SallaError, get_client

logger = logging.getLogger(__name__)
salla_bp = Blueprint("salla", __name__, url_prefix="/api/salla")


def _ok(data=None, status: int = 200, **extra):
    p = {"success": True}
    if data is not None:
        p["data"] = data
    p.update(extra)
    return jsonify(p), status


def _err(msg: str, status: int = 400):
    return jsonify({"success": False, "error": msg}), status


@salla_bp.route("/status", methods=["GET"])
def status():
    try:
        store = get_client().get_store().get("data", {})
        return _ok({"connected": True, "store": store.get("name"), "domain": store.get("domain")})
    except SallaError as e:
        return _ok({"connected": False, "error": str(e)})


@salla_bp.route("/products", methods=["GET"])
def list_products():
    try:
        page = int(request.args.get("page", 1))
        per_page = min(int(request.args.get("per_page", 50)), 100)
        keyword = request.args.get("keyword", "")
        result = get_client().list_products(page, per_page, keyword)
        return _ok(result.get("data", []), total=result.get("metadata", {}).get("total", 0))
    except SallaError as e:
        return _err(str(e), e.status_code or 400)


@salla_bp.route("/products/<int:product_id>", methods=["GET"])
def get_product(product_id: int):
    try:
        return _ok(get_client().get_product(product_id).get("data"))
    except SallaError as e:
        return _err(str(e), e.status_code or 400)


@salla_bp.route("/products", methods=["POST"])
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
        return _ok(result.get("data"), status=201)
    except SallaError as e:
        return _err(str(e), e.status_code or 400)


@salla_bp.route("/products/<int:product_id>", methods=["PUT"])
def update_product(product_id: int):
    body = request.get_json(silent=True) or {}
    try:
        return _ok(get_client().update_product(product_id, **body).get("data"))
    except SallaError as e:
        return _err(str(e), e.status_code or 400)


@salla_bp.route("/orders", methods=["GET"])
def list_orders():
    try:
        result = get_client().list_orders(
            page=int(request.args.get("page", 1)),
            per_page=min(int(request.args.get("per_page", 50)), 100),
            status=request.args.get("status", ""),
        )
        return _ok(result.get("data", []))
    except SallaError as e:
        return _err(str(e), e.status_code or 400)


@salla_bp.route("/orders/<int:order_id>", methods=["GET"])
def get_order(order_id: int):
    try:
        return _ok(get_client().get_order(order_id).get("data"))
    except SallaError as e:
        return _err(str(e), e.status_code or 400)


@salla_bp.route("/orders/<int:order_id>/status", methods=["PUT"])
def update_order_status(order_id: int):
    body = request.get_json(silent=True) or {}
    status_val = body.get("status", "")
    if not status_val:
        return _err("status is required")
    try:
        return _ok(get_client().update_order_status(order_id, status_val).get("data"))
    except SallaError as e:
        return _err(str(e), e.status_code or 400)


@salla_bp.route("/customers", methods=["GET"])
def list_customers():
    try:
        result = get_client().list_customers(
            page=int(request.args.get("page", 1)),
            per_page=min(int(request.args.get("per_page", 50)), 100),
        )
        return _ok(result.get("data", []))
    except SallaError as e:
        return _err(str(e), e.status_code or 400)


@salla_bp.route("/categories", methods=["GET"])
def list_categories():
    try:
        return _ok(get_client().list_categories().get("data", []))
    except SallaError as e:
        return _err(str(e), e.status_code or 400)


@salla_bp.route("/sync/pull", methods=["POST"])
def sync_pull():
    """Import Salla products + customers into local DB."""
    from ecommerce.models import db, Product, Category, Customer
    from core.app import app
    client = get_client()
    created = updated = 0
    try:
        with app.app_context():
            resp = client.list_products(per_page=100)
            for sp in resp.get("data", []):
                sku = sp.get("sku") or str(sp.get("id", ""))
                price = float(sp.get("price", {}).get("amount", 0) if isinstance(sp.get("price"), dict) else sp.get("price", 0))
                existing = Product.query.filter_by(sku=f"salla:{sku}").first()
                if existing:
                    existing.name = sp.get("name", existing.name)
                    existing.price = price
                    existing.stock = int(sp.get("quantity", existing.stock))
                    updated += 1
                else:
                    p = Product(
                        name=sp.get("name", ""),
                        description=sp.get("description", ""),
                        price=price,
                        stock=int(sp.get("quantity", 0)),
                        sku=f"salla:{sku}",
                        image_url=(sp.get("images") or [{}])[0].get("url", "") if sp.get("images") else "",
                    )
                    db.session.add(p)
                    created += 1
            db.session.commit()
        return _ok({"products": {"created": created, "updated": updated}})
    except SallaError as e:
        return _err(str(e), e.status_code or 400)
