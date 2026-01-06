"""Worker thread helpers for the desktop UI."""
from __future__ import annotations

from typing import Iterable, Optional, Sequence

from PySide6.QtCore import QObject, Signal

from tasmota.core.bulk import TasmotaBulkExecutor


class Worker(QObject):
    """Qt worker that wraps :class:`TasmotaBulkExecutor`."""

    progress = Signal(int, int)
    log_line = Signal(str, str)
    finished = Signal(object)

    def __init__(
        self,
        ips: Iterable[str],
        threads: int,
        out_dir: str,
        timeout: float,
        retries: int,
        backoff: float,
        send_backlog: bool,
        commands: Sequence[str],
        do_upgrade: bool = False,
        selected_ips: Optional[Sequence[str]] = None,
        ota_urls: Optional[Sequence[str]] = None,
        info_mode: str = "full",
        cmd_ips: Optional[Sequence[str]] = None,
        fw_ips: Optional[Sequence[str]] = None,
    ) -> None:
        super().__init__()
        self.executor = TasmotaBulkExecutor(
            ips,
            threads,
            out_dir,
            timeout,
            retries,
            backoff,
            send_backlog,
            commands,
            do_upgrade=do_upgrade,
            selected_ips=selected_ips,
            ota_urls=ota_urls,
            info_mode=info_mode,
            cmd_ips=cmd_ips,
            fw_ips=fw_ips,
            progress_callback=self.progress.emit,
            log_callback=self.log_line.emit,
        )

    def run(self) -> None:
        """Execute the queued tasks and emit the completion signal."""
        result = None
        try:
            result = self.executor.run()
        except Exception as exc:
            # Log error but don't crash - always emit finished
            try:
                self.log_line.emit(f"[ERROR] Worker failed: {exc}", "ERROR")
            except Exception:
                pass  # If even logging fails, still emit finished
        finally:
            self.finished.emit(result)  # Always emit to prevent UI hang
