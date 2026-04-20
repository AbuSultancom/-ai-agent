"""Slack & Discord integration — send messages, notifications, and results."""

import json
import logging
import os
import threading

import requests

logger = logging.getLogger(__name__)

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")


# ── Slack ─────────────────────────────────────────────────────────────────────

def send_slack_message(text: str, channel: str = "", webhook_url: str = "",
                       blocks: list | None = None) -> dict:
    url = webhook_url or SLACK_WEBHOOK_URL
    token = SLACK_BOT_TOKEN

    if not url and not token:
        return {"error": "SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN not configured"}

    if token and channel:
        try:
            from slack_sdk import WebClient
            client = WebClient(token=token)
            resp = client.chat_postMessage(channel=channel, text=text,
                                            blocks=blocks or [])
            return {"ok": True, "ts": resp["ts"], "channel": resp["channel"]}
        except ImportError:
            pass

    payload: dict = {"text": text}
    if blocks:
        payload["blocks"] = blocks

    try:
        r = requests.post(url, json=payload, timeout=10)
        return {"ok": r.ok, "status_code": r.status_code, "text": r.text[:200]}
    except Exception as exc:
        return {"error": str(exc)}


def send_slack_file(channel: str, filename: str, content: str, title: str = "") -> dict:
    token = SLACK_BOT_TOKEN
    if not token:
        return {"error": "SLACK_BOT_TOKEN not configured"}
    try:
        from slack_sdk import WebClient
        client = WebClient(token=token)
        resp = client.files_upload_v2(
            channel=channel,
            filename=filename,
            content=content,
            title=title or filename,
        )
        return {"ok": True, "file_id": resp["file"]["id"]}
    except ImportError:
        return {"error": "slack-sdk not installed. pip install slack-sdk"}
    except Exception as exc:
        return {"error": str(exc)}


# ── Discord ───────────────────────────────────────────────────────────────────

def send_discord_message(text: str, webhook_url: str = "",
                          username: str = "AI Agent", embeds: list | None = None) -> dict:
    url = webhook_url or DISCORD_WEBHOOK_URL
    if not url:
        return {"error": "DISCORD_WEBHOOK_URL not configured"}

    MAX = 2000
    chunks = [text[i:i+MAX] for i in range(0, len(text), MAX)] if len(text) > MAX else [text]

    results = []
    for chunk in chunks:
        payload: dict = {"username": username, "content": chunk}
        if embeds and chunk == chunks[0]:
            payload["embeds"] = embeds
        try:
            r = requests.post(url, json=payload, timeout=10)
            results.append({"ok": r.ok, "status_code": r.status_code})
        except Exception as exc:
            results.append({"error": str(exc)})

    return {"ok": all(r.get("ok") for r in results), "results": results}


def send_discord_embed(title: str, description: str, color: int = 0x6c63ff,
                        fields: list[dict] | None = None,
                        webhook_url: str = "") -> dict:
    embed = {
        "title": title,
        "description": description[:4096],
        "color": color,
        "fields": fields or [],
    }
    return send_discord_message("", webhook_url=webhook_url, embeds=[embed])


# ── Unified notify ────────────────────────────────────────────────────────────

def notify(message: str, channels: list[str] | None = None) -> dict:
    """Send a notification to all configured channels."""
    channels = channels or ["slack", "discord"]
    results = {}
    threads = []

    def _slack():
        results["slack"] = send_slack_message(message)

    def _discord():
        results["discord"] = send_discord_message(message)

    if "slack" in channels and (SLACK_WEBHOOK_URL or SLACK_BOT_TOKEN):
        t = threading.Thread(target=_slack)
        threads.append(t)
        t.start()

    if "discord" in channels and DISCORD_WEBHOOK_URL:
        t = threading.Thread(target=_discord)
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=15)

    return results
