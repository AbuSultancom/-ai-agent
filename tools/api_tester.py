"""API Testing Tool — test any HTTP API with AI-generated assertions."""

import json
import logging
import time
from typing import Any

import requests

from core import model_router

logger = logging.getLogger(__name__)


class APITester:

    def request(
        self,
        method: str,
        url: str,
        headers: dict | None = None,
        body: Any = None,
        timeout: int = 30,
    ) -> dict:
        method = method.upper()
        headers = headers or {}
        start = time.time()
        try:
            resp = requests.request(
                method,
                url,
                headers=headers,
                json=body if isinstance(body, (dict, list)) else None,
                data=body if isinstance(body, str) else None,
                timeout=timeout,
            )
            elapsed = round((time.time() - start) * 1000)
            try:
                resp_body = resp.json()
            except Exception:
                resp_body = resp.text[:5000]
            return {
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body": resp_body,
                "elapsed_ms": elapsed,
                "ok": resp.ok,
            }
        except Exception as exc:
            return {"error": str(exc), "ok": False}

    def analyze_response(self, request_info: dict, response: dict, expectations: str = "") -> str:
        prompt = (
            f"API Request:\n{json.dumps(request_info, indent=2)}\n\n"
            f"Response:\n{json.dumps(response, indent=2)}\n\n"
        )
        if expectations:
            prompt += f"Expected behavior: {expectations}\n\n"
        prompt += (
            "Analyze this API response. Identify:\n"
            "1. Whether the request succeeded\n"
            "2. Any errors or anomalies\n"
            "3. Response quality and structure\n"
            "4. Suggestions for improvement\n"
            "Be concise and actionable."
        )
        result = model_router.chat([{"role": "user", "content": prompt}], max_tokens=2048)
        return result if isinstance(result, str) else "".join(result)

    def run_test_suite(self, tests: list[dict]) -> list[dict]:
        results = []
        for test in tests:
            method = test.get("method", "GET")
            url = test.get("url", "")
            headers = test.get("headers", {})
            body = test.get("body")
            expectations = test.get("expectations", "")
            name = test.get("name", f"{method} {url}")

            response = self.request(method, url, headers, body)
            analysis = self.analyze_response(
                {"method": method, "url": url, "headers": headers, "body": body},
                response,
                expectations,
            )
            passed = response.get("ok", False)
            results.append({
                "name": name,
                "passed": passed,
                "response": response,
                "analysis": analysis,
            })
        return results
