"""OTA upgrade helpers."""

from __future__ import annotations

import asyncio
from typing import Dict, Optional

import httpx

from .network import collect_device_info, send_command

DEFAULT_OTA_URLS = {
    "ESP32": "http://ota.tasmota.com/tasmota32/release/tasmota32.bin",
    "ESP8266": "http://ota.tasmota.com/tasmota/release/tasmota.bin.gz",
}


async def perform_ota_upgrade(
    client: httpx.AsyncClient,
    ip: str,
    *,
    hardware: str,
    log,
    timeout: float,
    retries: int,
    backoff: float,
    ota_urls: Optional[Dict[str, str]] = None,
    info_mode: str = "full",
) -> bool:
    """Execute the OTA upgrade sequence for a device."""
    urls = dict(DEFAULT_OTA_URLS)
    if ota_urls:
        urls.update(ota_urls)

    hw_upper = (hardware or "").upper()
    target_url = urls["ESP32"] if "ESP32" in hw_upper else urls["ESP8266"]

    log(f"Sending OTA upgrade: {target_url}", tag="OTA")
    await send_command(
        client,
        ip,
        f"OtaUrl {target_url}",
        timeout=timeout,
        retries=retries,
        backoff=backoff,
        expect_json=False,
    )
    await send_command(
        client,
        ip,
        "Upgrade 1",
        timeout=timeout,
        retries=retries,
        backoff=backoff,
        expect_json=False,
    )

    log("Waiting 120s for OTA process...", tag="OTA")
    await asyncio.sleep(120)

    log("Sending Restart 1", tag="OTA")
    await send_command(
        client,
        ip,
        "Restart 1",
        timeout=timeout,
        retries=retries,
        backoff=backoff,
        expect_json=False,
    )
    await asyncio.sleep(1)

    for _ in range(18):  # 18 * 5s = 90s
        await asyncio.sleep(5)
        try:
            info = await collect_device_info(
                client,
                ip,
                timeout=timeout,
                retries=retries,
                backoff=backoff,
                info_mode=info_mode,
            )
        except Exception:
            continue

        if info.Ok:
            log(f"Device online, running FW: {info.Version}", tag="OTA")
            default_url = DEFAULT_OTA_URLS["ESP32"] if "ESP32" in hw_upper else DEFAULT_OTA_URLS["ESP8266"]
            await send_command(
                client,
                ip,
                f"OtaUrl {default_url}",
                timeout=timeout,
                retries=retries,
                backoff=backoff,
                expect_json=False,
            )
            log(f"Re-applied official OTA URL: {default_url}", tag="OTA")
            return True

    return False

