from __future__ import annotations

from typing import Any

import aiohttp

from .config import Settings


class YooKassaError(RuntimeError):
    pass


class YooKassaClient:
    api_url = "https://api.yookassa.ru/v3"

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return self.settings.yookassa_ready

    async def create_payment(
        self,
        *,
        order_id: int,
        tg_id: int,
        tariff_code: str,
        title: str,
        amount_rub: int,
    ) -> dict[str, Any]:
        if not self.configured:
            raise YooKassaError("YooKassa is not configured")

        payload = {
            "amount": {
                "value": f"{amount_rub:.2f}",
                "currency": "RUB",
            },
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": self.settings.yookassa_return_url,
            },
            "description": f"Karipuza VPN: {title}, заказ #{order_id}"[:128],
            "metadata": {
                "order_id": str(order_id),
                "tg_id": str(tg_id),
                "tariff_code": tariff_code,
            },
        }
        headers = {"Idempotence-Key": f"karipuza-order-{order_id}"[:64]}
        return await self._request("POST", "/payments", json=payload, headers=headers)

    async def get_payment(self, payment_id: str) -> dict[str, Any]:
        if not self.configured:
            raise YooKassaError("YooKassa is not configured")
        return await self._request("GET", f"/payments/{payment_id}")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=20)
        auth = aiohttp.BasicAuth(
            self.settings.yookassa_shop_id,
            self.settings.yookassa_secret_key,
        )
        async with aiohttp.ClientSession(timeout=timeout, auth=auth) as session:
            async with session.request(
                method,
                f"{self.api_url}{path}",
                json=json,
                headers=headers,
            ) as response:
                body = await response.text()
                try:
                    data = await response.json(content_type=None)
                except Exception:
                    data = {"raw": body}
                if response.status >= 400:
                    raise YooKassaError(
                        f"YooKassa HTTP {response.status}: {str(data)[:500]}"
                    )
                if not isinstance(data, dict):
                    raise YooKassaError("YooKassa returned a non-object response")
                return data
