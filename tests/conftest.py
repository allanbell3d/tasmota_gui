"""Shared fixtures: a fake Tasmota device served through httpx.MockTransport."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

import httpx
import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def status0(name="Kitchen", version="15.0.1(release-tasmota)", hardware="ESP8266EX", ip="10.0.0.5"):
    return {
        "Status": {"DeviceName": name, "Module": 0, "Topic": name.lower(), "FriendlyName": [name], "TelePeriod": 30},
        "StatusFWR": {"Version": version, "Core": "2_7_8", "SDK": "2.2.2", "Hardware": hardware},
        "StatusNET": {"Hostname": name.lower(), "Mac": "AA:BB:CC:DD:EE:FF", "IPAddress": ip, "Gateway": "10.0.0.1"},
        "StatusMQT": {"MqttClient": "DVES_1"},
        "StatusPRM": {"Uptime": "1T00:00:00", "OtaUrl": "http://ota.tasmota.com/tasmota/release/tasmota.bin.gz"},
        "StatusMEM": {"FlashSize": 4096, "FreeMem": 20},
        "StatusSTS": {"Wifi": {"RSSI": 80}},
    }


class FakeNetwork:
    """Routes /cm requests to per-IP handlers and records every command."""

    def __init__(self) -> None:
        self.devices: Dict[str, Callable[[str, httpx.Request], httpx.Response]] = {}
        self.log: List[tuple] = []

    def add_device(self, ip: str, handler: Optional[Callable[[str, httpx.Request], httpx.Response]] = None, **status_kwargs):
        def default(cmd: str, request: httpx.Request) -> httpx.Response:
            if cmd.lower() == "status 0":
                return httpx.Response(200, json=status0(ip=ip, **status_kwargs))
            return httpx.Response(200, json={cmd.split(" ")[0]: "Done"})

        self.devices[ip] = handler or default

    def commands_for(self, ip: str) -> List[str]:
        return [cmd for host, cmd, _ in self.log if host == ip]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        cmd = request.url.params.get("cmnd", "")
        self.log.append((host, cmd, dict(request.url.params)))
        handler = self.devices.get(host)
        if handler is None:
            raise httpx.ConnectTimeout("timed out", request=request)
        return handler(cmd, request)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


@pytest.fixture
def network() -> FakeNetwork:
    return FakeNetwork()


def json_response(payload) -> httpx.Response:
    return httpx.Response(200, content=json.dumps(payload).encode(), headers={"content-type": "application/json"})
