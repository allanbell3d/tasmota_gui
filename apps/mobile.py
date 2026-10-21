"""CLI entrypoint for the mobile (Kivy) interface."""

try:
    from apps import _bootstrap  # noqa: F401  (python -m apps.mobile)
except ImportError:  # run as a script: apps/ itself is on sys.path
    import _bootstrap  # noqa: F401

from tasmota.ui.mobile import main as run_mobile  # noqa: E402


def main() -> None:
    """Launch the mobile GUI."""
    run_mobile()


if __name__ == "__main__":
    main()
