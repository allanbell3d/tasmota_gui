"""CLI entrypoint for the desktop (PySide6) interface."""

try:
    from apps import _bootstrap  # noqa: F401  (python -m apps.desktop)
except ImportError:  # run as a script: apps/ itself is on sys.path
    import _bootstrap  # noqa: F401

from tasmota.ui.desktop.app import main as run_desktop  # noqa: E402


def main() -> None:
    """Launch the desktop GUI."""
    run_desktop()


if __name__ == "__main__":
    main()
