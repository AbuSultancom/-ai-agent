"""Webhook and Email notifications — fire when tasks complete."""

import json
import logging
import os
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

logger = logging.getLogger(__name__)

# ── Webhook ───────────────────────────────────────────────────────────────────

_webhooks_lock = threading.Lock()
_webhooks: list[dict] = []  # [{id, url, events, secret}]


def register_webhook(url: str, events: list[str] | None = None, secret: str = "") -> dict:
    import uuid
    wh = {
        "id": uuid.uuid4().hex[:10],
        "url": url,
        "events": events or ["task.completed", "task.failed"],
        "secret": secret,
    }
    with _webhooks_lock:
        _webhooks.append(wh)
    return wh


def remove_webhook(wh_id: str) -> bool:
    with _webhooks_lock:
        before = len(_webhooks)
        _webhooks[:] = [w for w in _webhooks if w["id"] != wh_id]
        return len(_webhooks) < before


def list_webhooks() -> list[dict]:
    with _webhooks_lock:
        return [{"id": w["id"], "url": w["url"], "events": w["events"]} for w in _webhooks]


def _sign_payload(secret: str, payload: bytes) -> str:
    import hashlib
    import hmac
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def _fire_webhook(wh: dict, event: str, data: dict) -> None:
    payload = json.dumps({"event": event, "data": data}).encode()
    headers = {"Content-Type": "application/json", "X-AI-Agent-Event": event}
    if wh.get("secret"):
        headers["X-Signature"] = _sign_payload(wh["secret"], payload)
    try:
        r = requests.post(wh["url"], data=payload, headers=headers, timeout=10)
        logger.info("Webhook %s → %s (%d)", event, wh["url"], r.status_code)
    except Exception as exc:
        logger.warning("Webhook delivery failed to %s: %s", wh["url"], exc)


def dispatch_event(event: str, data: dict) -> None:
    """Fire all webhooks that subscribed to this event (async)."""
    with _webhooks_lock:
        targets = [w for w in _webhooks if event in w.get("events", [])]
    for wh in targets:
        t = threading.Thread(target=_fire_webhook, args=(wh, event, data), daemon=True)
        t.start()

    # Also send email if configured
    if os.getenv("NOTIFY_EMAIL"):
        subject = f"AI Agent: {event}"
        body = f"Event: {event}\n\n{json.dumps(data, indent=2, ensure_ascii=False)}"
        _send_email_async(os.getenv("NOTIFY_EMAIL"), subject, body)


# ── Email ─────────────────────────────────────────────────────────────────────

def _send_email(to: str, subject: str, body: str) -> bool:
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    from_addr = os.getenv("SMTP_FROM", smtp_user)

    if not smtp_host or not smtp_user:
        logger.warning("SMTP not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASS.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to
        msg.attach(MIMEText(body, "plain", "utf-8"))
        html_body = f"<pre style='font-family:monospace'>{body}</pre>"
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, to, msg.as_string())
        logger.info("Email sent to %s: %s", to, subject)
        return True
    except Exception as exc:
        logger.warning("Email failed: %s", exc)
        return False


def _send_email_async(to: str, subject: str, body: str) -> None:
    threading.Thread(target=_send_email, args=(to, subject, body), daemon=True).start()


def send_email(to: str, subject: str, body: str) -> str:
    ok = _send_email(to, subject, body)
    return "✅ Email sent" if ok else "❌ Email failed (check SMTP config)"
