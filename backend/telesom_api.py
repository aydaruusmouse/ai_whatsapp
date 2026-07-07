"""HTTP client for Telesom WhatsApp business APIs."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE = (os.getenv("TELESOM_WHATSAPP_API_BASE") or "https://whatsapp.telesom.com").rstrip("/")
_TIMEOUT = float(os.getenv("TELESOM_API_TIMEOUT", "30"))


class TelesomAPIError(Exception):
    def __init__(
        self,
        message: str,
        *,
        timeout: bool = False,
        status_code: int | None = None,
        body: str | None = None,
    ):
        super().__init__(message)
        self.timeout = timeout
        self.status_code = status_code
        self.body = body


_CUSTOMER_API_UNAVAILABLE = (
    "Waan ka xunnahay, kuma caawin karnaa hadda — fadlan mar kale isku day."
)


def _friendly_api_error(exc: TelesomAPIError) -> str:
    return _CUSTOMER_API_UNAVAILABLE


def _parse_response(r: httpx.Response, path: str, url: str) -> dict[str, Any]:
    ct = (r.headers.get("content-type") or "").lower()
    if "json" not in ct:
        body = (r.text or "")[:500]
        logger.warning(
            "Telesom API non-JSON %s %s content-type=%s body=%s",
            path,
            url,
            ct,
            body,
        )
        raise TelesomAPIError(
            "Non-JSON response (incomplete or invalid request body?)",
            status_code=r.status_code,
            body=body,
        )
    try:
        data = r.json()
    except json.JSONDecodeError as e:
        body = (r.text or "")[:500]
        logger.warning("Telesom API JSON decode failed %s %s body=%s", path, url, body)
        raise TelesomAPIError(
            "Invalid JSON response",
            status_code=r.status_code,
            body=body,
        ) from e
    if isinstance(data, dict):
        return data
    return {"raw": data}


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{BASE}{path}"
    logger.info("Telesom API POST %s payload=%s", path, payload)
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            r = client.post(url, json=payload, headers={"Content-Type": "application/json"})
            r.raise_for_status()
            return _parse_response(r, path, url)
    except httpx.TimeoutException as e:
        logger.warning("Telesom API timeout POST %s", url)
        raise TelesomAPIError(f"Timeout calling {path}", timeout=True) from e
    except httpx.HTTPStatusError as e:
        body = (e.response.text or "")[:500]
        logger.warning("Telesom API HTTP %s POST %s body=%s", e.response.status_code, url, body)
        raise TelesomAPIError(
            f"HTTP {e.response.status_code}",
            status_code=e.response.status_code,
            body=body,
        ) from e
    except httpx.HTTPError as e:
        logger.warning("Telesom API error POST %s: %s", url, e)
        raise TelesomAPIError(str(e)) from e


def _get(path: str) -> dict[str, Any]:
    url = f"{BASE}{path}"
    logger.info("Telesom API GET %s", path)
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            r = client.get(url)
            r.raise_for_status()
            return _parse_response(r, path, url)
    except httpx.TimeoutException as e:
        logger.warning("Telesom API timeout GET %s", url)
        raise TelesomAPIError(f"Timeout calling {path}", timeout=True) from e
    except httpx.HTTPStatusError as e:
        body = (e.response.text or "")[:500]
        logger.warning("Telesom API HTTP %s GET %s body=%s", e.response.status_code, url, body)
        raise TelesomAPIError(
            f"HTTP {e.response.status_code}",
            status_code=e.response.status_code,
            body=body,
        ) from e
    except httpx.HTTPError as e:
        logger.warning("Telesom API error GET %s: %s", url, e)
        raise TelesomAPIError(str(e)) from e


def check_subscription(msisdn: str, offer: str) -> dict[str, Any]:
    return _post("/api/check-subscription", {"msisdn": msisdn, "offer": offer})


def subscribe(msisdn: str, offer: str) -> dict[str, Any]:
    return _post("/api/subscribe", {"msisdn": msisdn, "offer": offer})


def unsubscribe(msisdn: str, offer: str) -> dict[str, Any]:
    return _post("/api/unsubscribe", {"msisdn": msisdn, "offer": offer})


def block_wrong_transaction(
    msisdn: str,
    transactionnumber: str,
    wrongnumber: str,
    currency_code: str,
) -> dict[str, Any]:
    return _post(
        "/api/block-wrong-transaction",
        {
            "msisdn": msisdn,
            "transactionnumber": transactionnumber,
            "wrongnumber": wrongnumber,
            "currency_code": currency_code,
        },
    )


def new_fiber_installation(
    callsub: str,
    *,
    address: str,
    speed: str,
    payment_method: str,
    tran_type: str,
    contact_number: str | None = None,
    price: int = 50,
    center: str = "Main",
    discount: int = 0,
    description: str = "New fiber installation request via WhatsApp bot",
) -> dict[str, Any]:
    phone = (callsub or "").strip()
    contact = (contact_number or phone).strip()
    payload = {
        "callsub": phone,
        "price": price,
        "paymentMethod": payment_method,
        "contactNumber": contact,
        "Address": address.strip(),
        "Center": center,
        "Discount": discount,
        "Speed": speed,
        "TranType": tran_type,
        "description": description,
    }
    return _post("/api/new-fiber-installation", payload)


def get_exchange_rate() -> dict[str, Any]:
    return _get("/exchange-rate")
