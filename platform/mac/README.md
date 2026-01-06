# macOS Packaging (Placeholder)

This directory is reserved for future macOS packaging assets. As of v0.1.9 the
desktop PySide6 launcher (`apps/desktop.py`) remains the recommended entry point
on macOS. When a native packaging workflow (e.g., PyInstaller, Briefcase, or
Xcode project files) is introduced, document the required tooling and build
commands here.

## Getting Started

1. Ensure you can run the shared desktop launcher locally:
   ```bash
   python -m apps.desktop
   ```
2. Capture any macOS-specific configuration, signing requirements, or
   dependencies in this folder as they are discovered.
3. Update the root `README.md` release checklist once macOS packaging steps are
   available.

Until dedicated scripts exist, keep this directory under version control to
track discussions, notes, or experimental assets related to macOS distribution.
