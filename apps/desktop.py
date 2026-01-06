"""CLI entrypoint for the desktop (PySide6) interface."""

from tasmota.ui.desktop.app import main as run_desktop


def main() -> None:
    """Launch the desktop GUI."""
    run_desktop()


if __name__ == "__main__":
    main()
