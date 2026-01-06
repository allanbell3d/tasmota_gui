"""Discovery configuration panel for the mobile UI."""

from __future__ import annotations

from typing import Callable, Dict, Optional

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.utils import platform

from tasmota.constants import (
    ANDROID_THREAD_DEFAULT,
    ANDROID_THREAD_MAX,
    DEFAULT_IP_RANGES,
    DEFAULT_RETRIES,
    DEFAULT_THREADS,
    DEFAULT_TIMEOUT,
    DESKTOP_THREAD_MAX,
)

from .widgets.common import BorderedGridLayout, format_progress

class DiscoveryPanel(BoxLayout):
    """Inputs for discovery settings."""

    info_mode = StringProperty("lite")

    def __init__(
        self,
        discover_callback: Callable[[Dict], None],
        cancel_callback: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(orientation="vertical", spacing=dp(8), **kwargs)
        self.discover_callback = discover_callback
        self.cancel_callback = cancel_callback
        self._busy = False

        self._default_threads = self._determine_default_threads()
        self._max_threads = self._determine_max_threads()

        self.thread_input = TextInput(
            text=str(self._default_threads), multiline=False, input_filter="int"
        )
        self.timeout_input = TextInput(text=str(DEFAULT_TIMEOUT), multiline=False, input_filter="float")
        self.retries_input = TextInput(text=str(DEFAULT_RETRIES), multiline=False, input_filter="int")
        self.range_input = TextInput(text=DEFAULT_IP_RANGES, size_hint_y=None, height=dp(120))

        self.progress_box = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=0,
            opacity=0,
            spacing=dp(4),
            padding=(0, dp(4)),
        )
        self.progress_label = Label(text="Scan Progress: 0%", size_hint_y=None, height=dp(24))
        self.progress_bar = ProgressBar(max=1, value=0, size_hint_y=None, height=dp(18))
        self.progress_box.add_widget(self.progress_label)
        self.progress_box.add_widget(self.progress_bar)
        self.add_widget(self.progress_box)

        header = Label(text="Discovery", size_hint_y=None, height=dp(36))
        self.add_widget(header)

        self.add_widget(Label(text="IP Ranges", size_hint_y=None, height=dp(32)))
        self.add_widget(self.range_input)

        grid = BorderedGridLayout(
            cols=2,
            size_hint_y=None,
            height=dp(152),
            row_default_height=dp(40),
            row_force_default=True,
            spacing=dp(8),
            padding=dp(8),
        )
        grid.add_widget(Label(text="Threads"))
        grid.add_widget(self.thread_input)
        grid.add_widget(Label(text="Timeout (s)"))
        grid.add_widget(self.timeout_input)
        grid.add_widget(Label(text="Retries"))
        grid.add_widget(self.retries_input)
        self.add_widget(grid)

        mode_box = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        self.mode_spinner = Spinner(text="Lite", values=("Lite", "Full"), size_hint=(None, 1), width=dp(140))
        self.mode_spinner.bind(text=self._on_mode_change)
        mode_box.add_widget(Label(text="Info Mode", size_hint=(0.6, 1)))
        mode_box.add_widget(self.mode_spinner)
        self.add_widget(mode_box)

        self.btn_discover = Button(text="Start Scan", size_hint_y=None, height=dp(60))
        self.btn_discover.bind(on_release=lambda *_: self._on_button_press())
        self.add_widget(self.btn_discover)

    def _on_button_press(self):
        if self._busy:
            if self.cancel_callback:
                self.cancel_callback()
        else:
            self._emit_discover()

    def _on_mode_change(self, spinner, value):
        self.info_mode = value.lower()

    def _emit_discover(self):
        if self.discover_callback:
            self.discover_callback(self.get_parameters())

    def get_parameters(self) -> Dict:
        return {
            "threads": self.get_thread_count(),
            "timeout": float(self.timeout_input.text or DEFAULT_TIMEOUT),
            "retries": int(self.retries_input.text or DEFAULT_RETRIES),
            "ip_ranges": self.range_input.text,
            "info_mode": self.info_mode,
        }

    def get_thread_count(self) -> int:
        threads = self.clamp_threads(self.thread_input.text)
        if str(threads) != self.thread_input.text:
            self.thread_input.text = str(threads)
        return threads

    def clamp_threads(self, value: Optional[int] = None) -> int:
        if isinstance(value, str):
            value = value.strip()
        if value in (None, ""):
            parsed = self._default_threads
        else:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                parsed = self._default_threads
        parsed = max(1, parsed)
        return min(parsed, self._max_threads)

    def _determine_default_threads(self) -> int:
        if platform == "android":
            return min(ANDROID_THREAD_DEFAULT, DEFAULT_THREADS)
        return DEFAULT_THREADS

    def _determine_max_threads(self) -> int:
        if platform == "android":
            return ANDROID_THREAD_MAX
        return DESKTOP_THREAD_MAX

    def set_busy(self, busy: bool):
        self._busy = bool(busy)
        self.thread_input.disabled = busy
        self.timeout_input.disabled = busy
        self.retries_input.disabled = busy
        self.range_input.disabled = busy
        self.mode_spinner.disabled = busy
        self.btn_discover.text = "Cancel Scan" if busy else "Start Scan"
        self.btn_discover.disabled = False
        if busy:
            self.show_progress()
        else:
            self.hide_progress()

    def _set_progress_visible(self, visible: bool):
        target_height = dp(58) if visible else 0
        self.progress_box.height = target_height
        self.progress_box.opacity = 1 if visible else 0

    def show_progress(self):
        self._set_progress_visible(True)

    def hide_progress(self):
        self._set_progress_visible(False)
        self.update_progress(0, 0)

    def update_progress(self, done: int, total: int):
        def _apply(_: float):
            pct, capped_done, capped_total = format_progress(done, total)
            self.progress_bar.max = max(capped_total, 1)
            self.progress_bar.value = capped_done
            self.progress_label.text = f"Progress: {capped_done} / {capped_total} ({pct}%)"

        Clock.schedule_once(_apply, 0)
