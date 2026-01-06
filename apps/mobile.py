"""CLI entrypoint for the mobile (Kivy) interface."""

from tasmota.ui.mobile import main as run_mobile


def main() -> None:
    """Launch the mobile GUI."""
    run_mobile()


if __name__ == "__main__":
    main()
