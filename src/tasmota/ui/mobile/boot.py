
"""Boot splash sequence for the mobile application."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Iterable, Optional

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.widget import Widget

__all__ = ["BootSequence", "LogoSplash"]


def _candidate_roots(module_path: Path) -> Iterable[Path]:
    """Yield possible root directories for bundled assets."""

    packaged_root = getattr(sys, "_MEIPASS", None)
    if packaged_root:
        yield Path(packaged_root)

    for parent in module_path.parents:
        yield parent


def _resolve_logo_path() -> str:
    """Return the path to the bundled splash logo image."""

    module_path = Path(__file__).resolve()

    for root in _candidate_roots(module_path):
        candidate = root / "assets" / "images" / "logo.png"
        if candidate.exists():
            return str(candidate)

    # Fallback to the historical repository layout relative to the source tree.
    if len(module_path.parents) >= 3:
        fallback = module_path.parents[3] / "assets" / "images" / "logo.png"
        if fallback.exists():
            return str(fallback)

    # Final fallback assumes the working directory is the project root.
    return "assets/images/logo.png"


class LogoSplash(FloatLayout):
    """Full-screen logo displayed during application boot."""

    def __init__(self, *, source: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (1, 1)

        if source is None:
            source = _resolve_logo_path()

        with self.canvas.before:
            self._background_color = Color(0, 0, 0, 1)
            self._background_rect = Rectangle(pos=self.pos, size=self.size)

        self._image = Image(
            source=source,
            allow_stretch=True,
            keep_ratio=False,
            size_hint=(1, 1),
            pos_hint={"center_x": 0.5, "center_y": 0.5},
        )
        self.add_widget(self._image)

        self.bind(pos=self._update_background, size=self._update_background)

    def _update_background(self, *_):
        self._background_rect.pos = self.pos
        self._background_rect.size = self.size


class BootSequence:
    """Handle displaying and hiding the boot splash overlay."""

    def __init__(self, *, splash: Optional[LogoSplash] = None, fade_duration: float = 0.4):
        self.splash = splash or LogoSplash()
        self.fade_duration = float(max(fade_duration, 0))
        self._container: Optional[FloatLayout] = None
        self._root: Optional[Widget] = None
        self._attached_at: float = 0.0
        self._animation: Optional[Animation] = None
        self._revealed = False
        self._scheduled_reveal = None

    def attach(self, root_widget: Widget) -> FloatLayout:
        """Return a container that overlays the splash on top of the root widget."""

        if self._container is not None:
            return self._container

        container = FloatLayout(size_hint=(1, 1))
        container.add_widget(root_widget)
        container.add_widget(self.splash)

        self._container = container
        self._root = root_widget
        self._attached_at = time.perf_counter()
        self.splash.opacity = 1
        self._revealed = False
        return container

    def reveal(self) -> None:
        """Fade out the splash overlay and remove it from the view hierarchy."""

        if self._revealed:
            return
        self._revealed = True

        if self.splash.parent is None:
            return

        def _start_fade(_: float) -> None:
            if self.splash.parent is None:
                return

            if self.fade_duration == 0:
                self._remove_splash()
                return

            self._animation = Animation(opacity=0, duration=self.fade_duration)
            self._animation.bind(on_complete=lambda *_: self._remove_splash())
            self._animation.start(self.splash)

        elapsed = time.perf_counter() - self._attached_at
        delay = max(0.0, 0.2 - elapsed)  # ensure the splash is visible briefly
        if delay:
            self._scheduled_reveal = Clock.schedule_once(_start_fade, delay)
        else:
            _start_fade(0)

    def _remove_splash(self) -> None:
        if self._scheduled_reveal is not None:
            self._scheduled_reveal.cancel()
            self._scheduled_reveal = None

        if self.splash.parent is not None:
            parent = self.splash.parent
            if parent is not None:
                parent.remove_widget(self.splash)
        self.splash.opacity = 1
        self._animation = None
