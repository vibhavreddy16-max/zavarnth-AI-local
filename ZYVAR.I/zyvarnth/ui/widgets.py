from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QFrame, QLabel, QProgressBar, QVBoxLayout, QWidget


class AvatarWidget(QWidget):
    """A software-rendered abstract holographic face with transcript-led mouth shapes."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(250, 250)
        self.state = "Ready"
        self.level = 0.0
        self._speech = ""
        self._audio_elapsed = 0.0
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(33)

    def set_state(self, value: str) -> None:
        self.state = value
        self.update()

    def set_level(self, value: float) -> None:
        self.level = max(0.0, min(1.0, value))
        self.update()

    def set_speech(self, text: str) -> None:
        if text:
            self._speech += text
            self._speech = self._speech[-1200:]

    def advance_audio(self, seconds: float) -> None:
        self._audio_elapsed += max(0.0, seconds)

    def end_speech(self) -> None:
        self._speech = ""
        self._audio_elapsed = 0.0

    def _animate(self) -> None:
        self._phase += 0.045 if self.state in {"Listening", "Speaking", "Thinking"} else 0.018
        self.update()

    def _mouth_shape(self) -> tuple[float, float]:
        if self.state != "Speaking" or not self._speech:
            return 20.0, 2.0
        index = int(self._audio_elapsed * 13.5) % len(self._speech)
        char = self._speech[index].lower()
        if char in "ou" or char in "оу":
            return 10.0, 13.0
        if char in "aeiæə" or char in "аеёиэяю":
            return 23.0, 9.0
        if char in "bmpfv" or char in "бмпфв":
            return 16.0, 2.2
        return 19.0, 4.5

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        radius = min(self.width(), self.height()) * 0.42
        pulse = 1 + math.sin(self._phase) * (0.012 + self.level * 0.035)
        radius *= pulse

        halo = QRadialGradient(cx, cy, radius * 1.35)
        halo.setColorAt(0, QColor(15, 136, 160, 40 + int(self.level * 45)))
        halo.setColorAt(0.66, QColor(9, 75, 94, 18))
        halo.setColorAt(1, QColor(8, 15, 22, 0))
        painter.setBrush(halo)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(int(cx - radius * 1.35), int(cy - radius * 1.35), int(radius * 2.7), int(radius * 2.7))

        line = QColor(61, 213, 230, 205 if self.state == "Listening" else 145)
        painter.setPen(QPen(QColor(42, 147, 173, 80), 1))
        painter.setBrush(QColor(10, 35, 47, 150))
        painter.drawEllipse(int(cx - radius * .74), int(cy - radius * .82), int(radius * 1.48), int(radius * 1.64))

        face = QPainterPath()
        face.moveTo(cx, cy - radius * .66)
        face.cubicTo(cx + radius * .64, cy - radius * .62, cx + radius * .60, cy + radius * .10, cx + radius * .32, cy + radius * .50)
        face.quadTo(cx, cy + radius * .76, cx - radius * .32, cy + radius * .50)
        face.cubicTo(cx - radius * .60, cy + radius * .10, cx - radius * .64, cy - radius * .62, cx, cy - radius * .66)
        painter.setPen(QPen(line, 1.6))
        painter.setBrush(QColor(15, 48, 62, 155))
        painter.drawPath(face)

        eye_y = cy - radius * .12
        eye_shift = math.sin(self._phase * .23) * 1.8
        painter.setPen(QPen(QColor(62, 225, 241, 210), 2))
        painter.drawLine(int(cx - radius * .43 + eye_shift), int(eye_y), int(cx - radius * .16 + eye_shift), int(eye_y))
        painter.drawLine(int(cx + radius * .16 + eye_shift), int(eye_y), int(cx + radius * .43 + eye_shift), int(eye_y))

        nose = QPainterPath()
        nose.moveTo(cx, eye_y + 3)
        nose.lineTo(cx - 4, cy + radius * .19)
        nose.lineTo(cx + 4, cy + radius * .19)
        painter.setPen(QPen(QColor(70, 174, 193, 150), 1))
        painter.drawPath(nose)

        width, height = self._mouth_shape()
        mouth_y = cy + radius * .35
        painter.setPen(QPen(QColor(96, 228, 239, 230), 1.4))
        painter.setBrush(QColor(31, 125, 146, 180 if height > 3 else 65))
        painter.drawEllipse(int(cx - width / 2), int(mouth_y - height / 2), int(width), int(max(3, height)))

        painter.setPen(QPen(QColor(55, 190, 209, 65), 1))
        for offset in (-1, 0, 1):
            y = cy + offset * radius * .58
            painter.drawLine(int(cx - radius * .82), int(y), int(cx + radius * .82), int(y))
        painter.end()


class WaveformWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.level = 0.0
        self.active = False
        self.phase = 0.0
        self.setFixedHeight(38)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(35)

    def set_level(self, value: float) -> None:
        self.level = max(0.0, min(1.0, value))
        self.active = True

    def set_active(self, active: bool) -> None:
        self.active = active

    def _tick(self) -> None:
        self.phase += .14
        self.level *= .84
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cy = self.height() / 2
        count = 48
        for i in range(count):
            ratio = i / (count - 1)
            envelope = math.sin(math.pi * ratio) ** .65
            activity = self.level * 17 + 1.4 if self.active else 0
            wobble = abs(math.sin(self.phase + i * .43)) * 4 if self.active else 0
            height = max(1, envelope * activity + wobble)
            x = (i + .5) * self.width() / count
            alpha = int(65 + 150 * envelope)
            painter.setPen(QPen(QColor(47, 204, 221, alpha), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(int(x), int(cy - height), int(x), int(cy + height))


class MetricCard(QFrame):
    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.title = QLabel(title.upper())
        self.title.setObjectName("Eyebrow")
        self.value = QLabel("—")
        self.value.setObjectName("Value")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.bar)

    def set_metric(self, value: float | None, detail: str | None = None) -> None:
        if value is None:
            self.value.setText("Unavailable")
            self.bar.setValue(0)
            return
        self.value.setText(detail or f"{value:.0f}%")
        self.bar.setValue(max(0, min(100, int(value))))


def small_label(text: str, muted: bool = False) -> QLabel:
    label = QLabel(text)
    if muted:
        label.setObjectName("Muted")
    return label

