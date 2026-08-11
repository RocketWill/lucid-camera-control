"""Run controller commands without blocking the Qt UI thread."""

from __future__ import annotations

from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, Signal, Slot

from lucid_camera_control.application.commands import ApplicationCommand
from lucid_camera_control.application.controller import ApplicationController


class _WorkerSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)


class _CommandWorker(QRunnable):
    def __init__(
        self,
        controller: ApplicationController,
        command: ApplicationCommand,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._command = command
        self.signals = _WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            events = self._controller.execute(self._command)
            self.signals.succeeded.emit((events, self._controller.snapshot))
        except Exception as exc:
            self.signals.failed.emit(str(exc) or type(exc).__name__)


class CommandBridge(QObject):
    """Serialize background commands and marshal results onto the UI thread."""

    snapshot_changed = Signal(object)
    command_completed = Signal(object)
    command_failed = Signal(str)
    busy_changed = Signal(bool)

    def __init__(
        self,
        controller: ApplicationController,
        thread_pool: QThreadPool | None = None,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._thread_pool = thread_pool or QThreadPool.globalInstance()
        self._busy = False
        self._active_worker: _CommandWorker | None = None

    @property
    def busy(self) -> bool:
        return self._busy

    def execute(self, command: ApplicationCommand) -> bool:
        if self._busy:
            return False
        self._set_busy(True)
        worker = _CommandWorker(self._controller, command)
        self._active_worker = worker
        worker.signals.succeeded.connect(
            self._on_succeeded,
            Qt.ConnectionType.QueuedConnection,
        )
        worker.signals.failed.connect(
            self._on_failed,
            Qt.ConnectionType.QueuedConnection,
        )
        self._thread_pool.start(worker)
        return True

    @Slot(object)
    def _on_succeeded(self, payload: object) -> None:
        events, snapshot = payload
        self._active_worker = None
        self._set_busy(False)
        self.snapshot_changed.emit(snapshot)
        self.command_completed.emit(events)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._active_worker = None
        self._set_busy(False)
        self.command_failed.emit(message)

    def _set_busy(self, value: bool) -> None:
        if self._busy == value:
            return
        self._busy = value
        self.busy_changed.emit(value)
