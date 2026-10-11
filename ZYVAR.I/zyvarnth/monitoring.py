from __future__ import annotations

import threading
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal


class TelemetryWorker(QThread):
    sample_ready = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, interval: float = 2.5, parent=None) -> None:
        super().__init__(parent)
        self.interval = interval
        self._stopping = threading.Event()

    def stop(self) -> None:
        self._stopping.set()

    def run(self) -> None:
        try:
            import psutil
            psutil.cpu_percent(interval=None)
            while not self._stopping.is_set():
                battery = psutil.sensors_battery()
                try:
                    temps = psutil.sensors_temperatures(fahrenheit=False)
                    values = [sensor.current for group in temps.values() for sensor in group if sensor.current is not None]
                except (AttributeError, OSError):
                    values = []
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage(Path.home().anchor or "/")
                self.sample_ready.emit({
                    "cpu": psutil.cpu_percent(interval=None),
                    "memory": memory.percent,
                    "memory_used": memory.used / (1024**3),
                    "memory_total": memory.total / (1024**3),
                    "disk": disk.percent,
                    "battery": battery.percent if battery else None,
                    "temperature": max(values) if values else None,
                })
                self._stopping.wait(self.interval)
        except Exception as exc:
            self.error.emit(str(exc).splitlines()[0][:240])

