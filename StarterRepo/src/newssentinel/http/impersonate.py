from __future__ import annotations

import asyncio
from typing import Any

from curl_cffi import requests


class ImpersonateHttpClient:
    """
    Thin async wrapper around curl_cffi requests with browser TLS impersonation.
    """

    def __init__(self, impersonate: str = "chrome", timeout: int = 30):
        self.impersonate = impersonate
        self.timeout = timeout
        self._session = requests.Session()

    async def get_json(self, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None):
        response = await self._request("GET", url, params=params, headers=headers)
        return response.json()

    async def get_text(self, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None):
        response = await self._request("GET", url, params=params, headers=headers)
        return response.text

    async def _request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ):
        def _do_request():
            return self._session.request(
                method,
                url,
                params=params,
                headers=headers or {},
                impersonate=self.impersonate,
                timeout=self.timeout,
            )

        response = await asyncio.to_thread(_do_request)
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code} for {url}")
        return response
