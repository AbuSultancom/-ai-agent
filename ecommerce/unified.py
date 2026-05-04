"""
Unified product/order layer — aggregates data from all connected stores.

Sources (enabled by env vars):
  local    — always available (SQLite)
  shopify  — SHOPIFY_ACCESS_TOKEN set
  salla    — SALLA_ACCESS_TOKEN set
  zid      — ZID_ACCESS_TOKEN set
"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _source_enabled(source: str) -> bool:
    from core.config import config
    return {
        "shopify": bool(config.SHOPIFY_STORE_DOMAIN and config.SHOPIFY_ACCESS_TOKEN),
        "salla":   bool(config.SALLA_ACCESS_TOKEN),
        "zid":     bool(config.ZID_ACCESS_TOKEN),
        "local":   True,
    }.get(source, False)


def enabled_sources() -> list[str]:
    return [s for s in ("local", "shopify", "salla", "zid") if _source_enabled(s)]


# ── unified product schema ────────────────────────────────────────────────────

def _normalize_shopify(p: dict) -> dict:
    variant = (p.get("variants") or [{}])[0]
    image   = (p.get("images")   or [{}])[0]
    return {
        "source": "shopify",
        "source_id": str(p.get("id", "")),
        "name": p.get("title", ""),
        "description": p.get("body_html", ""),
        "price": float(variant.get("price") or 0),
        "stock": int(variant.get("inventory_quantity") or 0),
        "sku": variant.get("sku", ""),
        "image_url": image.get("src", ""),
        "category": p.get("product_type", ""),
        "tags": p.get("tags", ""),
        "url": f"https://{p.get('handle', '')}",
    }


def _normalize_salla(p: dict) -> dict:
    price_field = p.get("price", {})
    price = float(price_field.get("amount", 0) if isinstance(price_field, dict) else price_field)
    imgs = p.get("images") or []
    return {
        "source": "salla",
        "source_id": str(p.get("id", "")),
        "name": p.get("name", ""),
        "description": p.get("description", ""),
        "price": price,
        "stock": int(p.get("quantity", 0)),
        "sku": p.get("sku", ""),
        "image_url": imgs[0].get("url", "") if imgs else "",
        "category": p.get("category", {}).get("name", "") if isinstance(p.get("category"), dict) else "",
        "tags": "",
        "url": p.get("url", ""),
    }


def _normalize_zid(p: dict) -> dict:
    name_field = p.get("name", {})
    name = name_field.get("ar") or name_field.get("en") or "" if isinstance(name_field, dict) else str(name_field)
    imgs = p.get("images") or []
    return {
        "source": "zid",
        "source_id": str(p.get("id", "")),
        "name": name,
        "description": "",
        "price": float(p.get("price", 0)),
        "stock": int(p.get("quantity", 0)),
        "sku": p.get("sku", ""),
        "image_url": imgs[0].get("url", "") if imgs else "",
        "category": "",
        "tags": "",
        "url": "",
    }


def _normalize_local(p) -> dict:
    return {
        "source": "local",
        "source_id": p.id,
        "name": p.name,
        "description": p.description,
        "price": p.price,
        "stock": p.stock,
        "sku": p.sku or "",
        "image_url": p.image_url or "",
        "category": p.category.name if p.category else "",
        "tags": "",
        "url": f"/store/products/{p.id}",
    }


# ── public API ────────────────────────────────────────────────────────────────

def get_all_products(search: str = "", limit: int = 100,
                     source_filter: str | None = None) -> list[dict]:
    """Return products from all enabled stores, normalized."""
    products: list[dict] = []
    sources = enabled_sources()
    if source_filter:
        sources = [s for s in sources if s == source_filter]

    if "local" in sources:
        try:
            from ecommerce.models import Product
            q = Product.query.filter_by(is_active=True)
            if search:
                q = q.filter(Product.name.ilike(f"%{search}%"))
            for p in q.limit(limit).all():
                products.append(_normalize_local(p))
        except Exception as e:
            logger.warning("Local products error: %s", e)

    if "shopify" in sources:
        try:
            from ecommerce.shopify.client import get_client as shopify_client
            result = shopify_client().list_products(limit=min(limit, 250))
            for p in result.get("products", []):
                n = _normalize_shopify(p)
                if not search or search.lower() in n["name"].lower():
                    products.append(n)
        except Exception as e:
            logger.warning("Shopify products error: %s", e)

    if "salla" in sources:
        try:
            from ecommerce.salla.client import get_client as salla_client
            result = salla_client().list_products(per_page=min(limit, 100), keyword=search)
            for p in result.get("data", []):
                products.append(_normalize_salla(p))
        except Exception as e:
            logger.warning("Salla products error: %s", e)

    if "zid" in sources:
        try:
            from ecommerce.zid.client import get_client as zid_client
            result = zid_client().list_products(per_page=min(limit, 100), search=search)
            for p in result.get("products", []):
                products.append(_normalize_zid(p))
        except Exception as e:
            logger.warning("Zid products error: %s", e)

    return products


def get_store_summary() -> dict[str, Any]:
    """Return a dashboard summary from all connected stores."""
    summary: dict[str, Any] = {"sources": {}}

    for source in enabled_sources():
        info: dict[str, Any] = {"connected": False}
        try:
            if source == "local":
                from ecommerce.models import Product, Order, Customer
                info = {
                    "connected": True,
                    "products": Product.query.filter_by(is_active=True).count(),
                    "orders": Order.query.count(),
                    "customers": Customer.query.count(),
                }
            elif source == "shopify":
                from ecommerce.shopify.client import get_client as c
                cl = c()
                info = {
                    "connected": True,
                    "products": cl.count_products(),
                    "orders": cl.count_orders(),
                    "customers": cl.count_customers(),
                }
            elif source == "salla":
                from ecommerce.salla.client import get_client as c
                store = c().get_store().get("data", {})
                info = {"connected": True, "store_name": store.get("name", "")}
            elif source == "zid":
                from ecommerce.zid.client import get_client as c
                store = c().get_store().get("store", {})
                info = {"connected": True, "store_name": store.get("name", "")}
        except Exception as e:
            info = {"connected": False, "error": str(e)}
        summary["sources"][source] = info

    return summary


def push_product_to_all(product_id: str) -> dict[str, Any]:
    """Push a local product to all connected external stores."""
    results: dict[str, Any] = {}

    if _source_enabled("shopify"):
        try:
            from ecommerce.shopify.sync import push_product
            results["shopify"] = push_product(product_id)
        except Exception as e:
            results["shopify"] = {"error": str(e)}

    if _source_enabled("salla"):
        try:
            from ecommerce.models import Product
            from core.app import app
            with app.app_context():
                p = Product.query.get(product_id)
                if p:
                    from ecommerce.salla.client import get_client
                    r = get_client().create_product(p.name, p.price, p.description, p.stock, p.sku or "")
                    results["salla"] = {"action": "created", "id": r.get("data", {}).get("id")}
        except Exception as e:
            results["salla"] = {"error": str(e)}

    if _source_enabled("zid"):
        try:
            from ecommerce.models import Product
            from core.app import app
            with app.app_context():
                p = Product.query.get(product_id)
                if p:
                    from ecommerce.zid.client import get_client
                    r = get_client().create_product(p.name, p.price, p.description, p.stock, p.sku or "")
                    results["zid"] = {"action": "created", "id": r.get("product", {}).get("id")}
        except Exception as e:
            results["zid"] = {"error": str(e)}

    return results
