from __future__ import annotations

import threading

from PyQt6.QtCore import QThread, pyqtSignal

from ..ai import GeminiService
from ..security import redact_sensitive_text
from ..tools.builtins import ToolExecutor


class ChatWorker(QThread):
    text_delta = pyqtSignal(str)
    completed = pyqtSignal(str)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, service: GeminiService, messages: list[dict[str, str]], image: bytes | None = None, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.messages = messages
        self.image = image
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            result = self.service.stream_reply(
                self.messages,
                on_text=self.text_delta.emit,
                cancel=self.cancel_event,
                image=self.image,
            )
            if self.cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(redact_sensitive_text(str(exc)))


class SearchWorker(QThread):
    results = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, executor: ToolExecutor, query: str, parent=None) -> None:
        super().__init__(parent)
        self.executor = executor
        self.query = query

    def run(self) -> None:
        try:
            self.results.emit(self.executor.web_search(self.query, 8))
        except Exception as exc:
            self.failed.emit(redact_sensitive_text(str(exc)))


class ScreenshotWorker(QThread):
    captured = pyqtSignal(bytes)
    failed = pyqtSignal(str)

    def run(self) -> None:
        try:
            from ..screen import capture_screenshot

            self.captured.emit(capture_screenshot())
        except Exception as exc:
            self.failed.emit(redact_sensitive_text(str(exc)))


class SingleToolWorker(QThread):
    approval_needed = pyqtSignal(str)
    completed = pyqtSignal(str)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, executor: ToolExecutor, name: str, arguments: dict, parent=None) -> None:
        super().__init__(parent)
        self.executor = executor
        self.name = name
        self.arguments = arguments
        self._approval = threading.Event()
        self._approved = False
        self._cancel = threading.Event()

    def answer_approval(self, approved: bool) -> None:
        self._approved = approved
        self._approval.set()

    def cancel(self) -> None:
        self._cancel.set()
        self._approval.set()

    def run(self) -> None:
        try:
            from ..tools.registry import ApprovalRequired
            try:
                result = self.executor.execute(self.name, self.arguments)
            except ApprovalRequired as request:
                self.approval_needed.emit(request.summary)
                while not self._cancel.is_set() and not self._approval.wait(0.1):
                    pass
                if self._cancel.is_set() or not self._approved:
                    self.cancelled.emit()
                    return
                result = self.executor.execute(self.name, self.arguments, approved=True)
            if self._cancel.is_set():
                self.cancelled.emit()
                return
            self.completed.emit(str(result)[:12000])
        except Exception as exc:
            self.failed.emit(redact_sensitive_text(str(exc)))

