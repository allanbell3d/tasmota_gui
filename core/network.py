"""Network helpers for interacting with Tasmota devices."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional, Tuple

import httpx

from .parser import DeviceResult, parse_status_payload, safe_extract_json


async def http_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout: float,
    retries: int,
    backoff: float,
) -> httpx.Response:
    """Fetch *url* with retry/backoff logic."""
    last_err = ""
    for attempt in range(1, max(1, retries) + 1):
        try:
            response = await client.get(url, timeout=timeout)
            if response.status_code == 200:
                return response
            last_err = f"HTTP {response.status_code}"
        except Exception as exc:  # pragma: no cover - network failure path
            last_err = str(exc)
        if attempt < retries:
            await asyncio.sleep((2 ** (attempt - 1)) * backoff)
    raise RuntimeError(last_err or "Request failed")


async def send_command(
    client: httpx.AsyncClient,
    ip: str,
    command: str,
    *,
    timeout: float,
    retries: int,
    backoff: float,
    expect_json: bool = True,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Send a command to a device and optionally parse JSON from the response."""
    params = httpx.QueryParams({"cmnd": command})
    url = f"http://{ip}/cm?{params}"
    response = await http_get(client, url, timeout=timeout, retries=retries, backoff=backoff)
    text = response.text
    return (safe_extract_json(text) if expect_json else None, text)


async def collect_device_info(
    client: httpx.AsyncClient,
    ip: str,
    *,
    timeout: float,
    retries: int,
    backoff: float,
    info_mode: str = "full",
) -> DeviceResult:
    """Collect detailed information for a Tasmota device."""
    try:
        status0, _ = await send_command(
            client,
            ip,
            "Status 0",
            timeout=timeout,
            retries=retries,
            backoff=backoff,
        )
    except Exception:
        return DeviceResult(IP=ip)

    if not isinstance(status0, dict):
        return DeviceResult(IP=ip)

    result = parse_status_payload(ip, status0, info_mode=info_mode)
    if not result.Ok or info_mode == "lite":
        return result

    try:
        status5, _ = await send_command(
            client,
            ip,
            "Status 5",
            timeout=timeout,
            retries=retries,
            backoff=backoff,
        )
    except Exception:
        status5 = None

    if isinstance(status5, dict):
        cfg = status5.get("StatusCFG") or status5.get("Status5") or {}
        templ = cfg.get("Template")
        if isinstance(templ, dict):
            result.TemplateName = (templ.get("NAME") or templ.get("Name") or "").strip()
        elif isinstance(templ, str):
            try:
                templ_json = safe_extract_json(templ)
                if isinstance(templ_json, dict):
                    result.TemplateName = (templ_json.get("NAME") or templ_json.get("Name") or "").strip()
                else:
                    result.TemplateName = templ.strip()
            except Exception:
                result.TemplateName = templ.strip()

    if not result.TemplateName:
        try:
            template, _ = await send_command(
                client,
                ip,
                "Template",
                timeout=timeout,
                retries=retries,
                backoff=backoff,
            )
        except Exception:
            template = None

        if isinstance(template, dict):
            result.TemplateName = (template.get("NAME") or template.get("Name") or "").strip()

    return result

