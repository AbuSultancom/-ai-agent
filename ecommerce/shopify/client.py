"""
Shopify Admin REST API client (API version 2024-01).

Requires environment variables:
  SHOPIFY_STORE_DOMAIN  e.g. my-store.myshopify.com
  SHOPIFY_ACCESS_TOKEN  Admin API access token
  SHOPIFY_API_VERSION   default: 2024-01
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

_API_VERSION = "2024-01"


class ShopifyError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class ShopifyClient:
    def __init__(self, store_domain: str, access_token: str, api_version: str = _API_VERSION):
        self.store_domain = store_domain.rstrip("/")
        self.access_token = access_token
        self.api_version = api_version
        self._session = requests.Session()
        self._session.headers.update({
            "X-Shopify-Access-Token": self.access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    @property
    def base_url(self) -> str:
        return f"https://{self.store_domain}/admin/api/{self.api_version}"

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            resp = self._session.request(method, url, timeout=30, **kwargs)
        except requests.RequestException as e:
            raise ShopifyError(f"Network error: {e}")

        if resp.status_code == 429:
            raise ShopifyError("Shopify rate limit exceeded", 429)
        if not resp.ok:
            try:
                detail = resp.json().get("errors", resp.text[:200])
            except Exception:
                detail = resp.text[:200]
            raise ShopifyError(f"Shopify API error {resp.status_code}: {detail}", resp.status_code)

        if resp.content:
            return resp.json()
        return {}

    def get(self, endpoint: str, params: dict | None = None) -> dict:
        return self._request("GET", endpoint, params=params)

    def post(self, endpoint: str, body: dict) -> dict:
        return self._request("POST", endpoint, json=body)

    def put(self, endpoint: str, body: dict) -> dict:
        return self._request("PUT", endpoint, json=body)

    def delete(self, endpoint: str) -> dict:
        return self._request("DELETE", endpoint)

    # ── Products ──────────────────────────────────────────────────────────────

    def list_products(self, limit: int = 50, page_info: str | None = None,
                      status: str = "active", **filters) -> dict:
        params: dict[str, Any] = {"limit": min(limit, 250), "status": status}
        if page_info:
            params["page_info"] = page_info
        params.update(filters)
        return self.get("products.json", params=params)

    def get_product(self, product_id: int) -> dict:
        return self.get(f"products/{product_id}.json")

    def create_product(self, title: str, body_html: str = "", vendor: str = "",
                       product_type: str = "", tags: str = "",
                       variants: list[dict] | None = None,
                       images: list[dict] | None = None) -> dict:
        payload: dict[str, Any] = {
            "product": {
                "title": title,
                "body_html": body_html,
                "vendor": vendor,
                "product_type": product_type,
                "tags": tags,
            }
        }
        if variants:
            payload["product"]["variants"] = variants
        if images:
            payload["product"]["images"] = images
        return self.post("products.json", payload)

    def update_product(self, product_id: int, **fields) -> dict:
        return self.put(f"products/{product_id}.json", {"product": {"id": product_id, **fields}})

    def delete_product(self, product_id: int) -> dict:
        return self.delete(f"products/{product_id}.json")

    def count_products(self) -> int:
        return self.get("products/count.json").get("count", 0)

    # ── Product Variants ──────────────────────────────────────────────────────

    def list_variants(self, product_id: int) -> dict:
        return self.get(f"products/{product_id}/variants.json")

    def update_variant(self, variant_id: int, **fields) -> dict:
        return self.put(f"variants/{variant_id}.json", {"variant": {"id": variant_id, **fields}})

    # ── Inventory ─────────────────────────────────────────────────────────────

    def list_inventory_levels(self, inventory_item_ids: list[int] | None = None,
                              location_ids: list[int] | None = None) -> dict:
        params: dict[str, Any] = {}
        if inventory_item_ids:
            params["inventory_item_ids"] = ",".join(str(i) for i in inventory_item_ids)
        if location_ids:
            params["location_ids"] = ",".join(str(i) for i in location_ids)
        return self.get("inventory_levels.json", params=params)

    def set_inventory_level(self, inventory_item_id: int, location_id: int, available: int) -> dict:
        return self.post("inventory_levels/set.json", {
            "inventory_item_id": inventory_item_id,
            "location_id": location_id,
            "available": available,
        })

    def list_locations(self) -> dict:
        return self.get("locations.json")

    # ── Collections ───────────────────────────────────────────────────────────

    def list_collections(self) -> dict:
        return self.get("custom_collections.json")

    def create_collection(self, title: str, body_html: str = "") -> dict:
        return self.post("custom_collections.json", {
            "custom_collection": {"title": title, "body_html": body_html}
        })

    # ── Customers ─────────────────────────────────────────────────────────────

    def list_customers(self, limit: int = 50, **filters) -> dict:
        params: dict[str, Any] = {"limit": min(limit, 250), **filters}
        return self.get("customers.json", params=params)

    def get_customer(self, customer_id: int) -> dict:
        return self.get(f"customers/{customer_id}.json")

    def create_customer(self, first_name: str, last_name: str, email: str,
                        phone: str = "", tags: str = "",
                        addresses: list[dict] | None = None) -> dict:
        payload: dict[str, Any] = {
            "customer": {
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "phone": phone,
                "tags": tags,
            }
        }
        if addresses:
            payload["customer"]["addresses"] = addresses
        return self.post("customers.json", payload)

    def update_customer(self, customer_id: int, **fields) -> dict:
        return self.put(f"customers/{customer_id}.json", {"customer": {"id": customer_id, **fields}})

    def count_customers(self) -> int:
        return self.get("customers/count.json").get("count", 0)

    # ── Orders ────────────────────────────────────────────────────────────────

    def list_orders(self, status: str = "any", limit: int = 50,
                    financial_status: str | None = None,
                    fulfillment_status: str | None = None, **filters) -> dict:
        params: dict[str, Any] = {"status": status, "limit": min(limit, 250)}
        if financial_status:
            params["financial_status"] = financial_status
        if fulfillment_status:
            params["fulfillment_status"] = fulfillment_status
        params.update(filters)
        return self.get("orders.json", params=params)

    def get_order(self, order_id: int) -> dict:
        return self.get(f"orders/{order_id}.json")

    def update_order(self, order_id: int, **fields) -> dict:
        return self.put(f"orders/{order_id}.json", {"order": {"id": order_id, **fields}})

    def close_order(self, order_id: int) -> dict:
        return self.post(f"orders/{order_id}/close.json", {})

    def cancel_order(self, order_id: int, reason: str = "other", email: bool = True) -> dict:
        return self.post(f"orders/{order_id}/cancel.json", {"reason": reason, "email": email})

    def count_orders(self, status: str = "any") -> int:
        return self.get("orders/count.json", params={"status": status}).get("count", 0)

    # ── Fulfillments ──────────────────────────────────────────────────────────

    def list_fulfillments(self, order_id: int) -> dict:
        return self.get(f"orders/{order_id}/fulfillments.json")

    def create_fulfillment(self, order_id: int, location_id: int,
                           tracking_number: str = "", tracking_company: str = "",
                           notify_customer: bool = True) -> dict:
        return self.post(f"orders/{order_id}/fulfillments.json", {
            "fulfillment": {
                "location_id": location_id,
                "tracking_number": tracking_number,
                "tracking_company": tracking_company,
                "notify_customer": notify_customer,
            }
        })

    # ── Discounts ─────────────────────────────────────────────────────────────

    def list_price_rules(self) -> dict:
        return self.get("price_rules.json")

    def create_price_rule(self, title: str, value: float, value_type: str = "percentage",
                          customer_selection: str = "all",
                          target_type: str = "line_item",
                          allocation_method: str = "across",
                          starts_at: str | None = None) -> dict:
        payload: dict[str, Any] = {
            "price_rule": {
                "title": title,
                "value_type": value_type,
                "value": str(value),
                "customer_selection": customer_selection,
                "target_type": target_type,
                "target_selection": "all",
                "allocation_method": allocation_method,
                "starts_at": starts_at or "2024-01-01T00:00:00Z",
            }
        }
        return self.post("price_rules.json", payload)

    def create_discount_code(self, price_rule_id: int, code: str) -> dict:
        return self.post(f"price_rules/{price_rule_id}/discount_codes.json",
                         {"discount_code": {"code": code}})

    # ── Shop info ─────────────────────────────────────────────────────────────

    def get_shop(self) -> dict:
        return self.get("shop.json")

    # ── Webhooks ──────────────────────────────────────────────────────────────

    def list_webhooks(self) -> dict:
        return self.get("webhooks.json")

    def create_webhook(self, topic: str, address: str, format: str = "json") -> dict:
        return self.post("webhooks.json", {
            "webhook": {"topic": topic, "address": address, "format": format}
        })

    def delete_webhook(self, webhook_id: int) -> dict:
        return self.delete(f"webhooks/{webhook_id}.json")

    # ── Metafields ────────────────────────────────────────────────────────────

    def list_metafields(self, resource: str, resource_id: int) -> dict:
        return self.get(f"{resource}/{resource_id}/metafields.json")

    def create_metafield(self, resource: str, resource_id: int,
                         namespace: str, key: str, value: str, type: str = "single_line_text_field") -> dict:
        return self.post(f"{resource}/{resource_id}/metafields.json", {
            "metafield": {"namespace": namespace, "key": key, "value": value, "type": type}
        })


def verify_webhook_signature(data: bytes, hmac_header: str, secret: str) -> bool:
    """Verify that a Shopify webhook request is authentic."""
    computed = hmac.new(secret.encode(), data, hashlib.sha256).hexdigest()
    import base64
    computed_b64 = base64.b64encode(bytes.fromhex(computed)).decode()
    return hmac.compare_digest(computed_b64, hmac_header)


def get_client() -> ShopifyClient:
    """Return a configured ShopifyClient from environment variables."""
    from core.config import config
    if not config.SHOPIFY_STORE_DOMAIN or not config.SHOPIFY_ACCESS_TOKEN:
        raise ShopifyError("SHOPIFY_STORE_DOMAIN and SHOPIFY_ACCESS_TOKEN must be set in .env")
    return ShopifyClient(
        store_domain=config.SHOPIFY_STORE_DOMAIN,
        access_token=config.SHOPIFY_ACCESS_TOKEN,
        api_version=config.SHOPIFY_API_VERSION,
    )
