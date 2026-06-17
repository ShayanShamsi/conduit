"""Milestone 1 — thin HTTP client over the Bitrefill Personal API.

Everything else in the project goes through `BitrefillClient.request`, which:
- attaches Bearer auth + JSON headers,
- unwraps the `{ meta, data }` envelope and returns `data`,
- raises a clean `BitrefillError` carrying `error_code` + `message` on failure.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.bitrefill.com/v2"


class BitrefillError(RuntimeError):
    """An API-level failure. Carries the structured error fields when present."""

    def __init__(self, status_code: int, error_code: str | None, message: str):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        super().__init__(f"[{status_code} {error_code or 'http_error'}] {message}")


class BitrefillClient:
    def __init__(self, api_key: str | None = None, *, timeout: float = 30.0):
        self.api_key = api_key or os.environ.get("BITREFILL_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "Missing BITREFILL_API_KEY. Put it in a .env file or the environment."
            )
        self._http = httpx.Client(
            base_url=BASE_URL,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        # Remembered from the last response so callers can respect quotas.
        self.last_headers: httpx.Headers | None = None

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Make a request and return the unwrapped `data` payload."""
        resp = self._http.request(method, path, params=params, json=json)
        self.last_headers = resp.headers

        try:
            body = resp.json()
        except ValueError:
            body = {}

        if not resp.is_success:
            raise BitrefillError(
                status_code=resp.status_code,
                error_code=body.get("error_code"),
                message=body.get("message", resp.text or resp.reason_phrase),
            )

        # Successful responses nest everything under `data`.
        return body.get("data", body)

    # --- convenience verbs ---------------------------------------------------
    def get(self, path: str, **kw: Any) -> Any:
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw: Any) -> Any:
        return self.request("POST", path, **kw)

    def ping(self) -> str:
        """GET /ping — returns 'pong' when the key works."""
        return self.get("/ping").get("message", "")

    def balance(self) -> dict[str, Any]:
        """GET /accounts/balance."""
        return self.get("/accounts/balance")

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "BitrefillClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


if __name__ == "__main__":
    # Milestone 1 smoke test: prove the key works.
    with BitrefillClient() as bf:
        print("ping ->", bf.ping())
        bal = bf.balance()
        print(f"balance -> {bal.get('balance')} {bal.get('currency')}")
