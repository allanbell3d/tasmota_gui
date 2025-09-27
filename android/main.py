"""Placeholder entry point for the future Kivy Android UI."""

from __future__ import annotations

from core.utils import build_ip_list


def demo_scan() -> list[str]:
    """Demonstrate importing shared logic from :mod:`core`."""
    return build_ip_list("192.168.0.1-3")


def main() -> None:
    """Temporary runner used while the Android UI is under development."""
    ips = demo_scan()
    print("Android GUI placeholder - shared utils available:", ips)


if __name__ == "__main__":  # pragma: no cover - manual invocation
    main()
