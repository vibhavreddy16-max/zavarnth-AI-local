from __future__ import annotations

import asyncio
import queue
import threading

from PyQt6.QtCore import QThread, pyqtSignal

from ..ai import SYSTEM_INSTRUCTION
from ..config import Settings, get_api_key
from ..security import redact_sensitive_text


class LiveVoiceWorker(QThread):
    status_changed = pyqtSignal(str)
    user_transcript = pyqtSignal(str)
    assistant_transcript = pyqtSignal(str)
    audio_level = pyqtSignal(float)
    audio_advanced = pyqtSignal(float)
    turn_finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._recording = threading.Event()
        self._stopping = threading.Event()

    def set_push_to_talk(self, active: bool) -> None:
        self._recording.set() if active else self._recording.clear()

    def stop(self) -> None:
        self._stopping.set()
        self._recording.clear()

    def run(self) -> None:
        try:
            asyncio.run(self._run_live())
        except Exception as exc:
            self.error.emit(_safe_error(exc))
            self.status_changed.emit("Error")

    async def _run_live(self) -> None:
        key = get_api_key()
        if not key:
            raise RuntimeError("Add a Gemini API key in Settings before starting voice.")
        try:
            import sounddevice as sd
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("Live voice dependencies are unavailable. Install the project dependencies.") from exc

        client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=60000))
        voice = self.settings.get("voice", "Aoede")
        config = {
            "response_modalities": ["AUDIO"],
            "input_audio_transcription": {},
            "output_audio_transcription": {},
            "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": voice}}},
            "system_instruction": SYSTEM_INSTRUCTION,
        }
        audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=24)
        input_stream = None
        output_stream = None

        def microphone_callback(indata, frames, timing, status) -> None:
            if self._recording.is_set() and not self._stopping.is_set():
                self.audio_level.emit(_amplitude(bytes(indata)))
                try:
                    audio_queue.put_nowait(bytes(indata))
                except queue.Full:
                    try:
                        audio_queue.get_nowait()
                        audio_queue.put_nowait(bytes(indata))
                    except queue.Empty:
                        pass

        try:
            input_device = _resolve_audio_device(sd, self.settings.get("input_device"), "input")
            output_device = _resolve_audio_device(sd, self.settings.get("output_device"), "output")
            output_stream = sd.RawOutputStream(
                samplerate=24000, channels=1, dtype="int16", device=output_device
            )
            output_stream.start()
            self.status_changed.emit("Connecting")
            async with client.aio.live.connect(model=self.settings.get("live_model", "gemini-3.8-live"), config=config) as session:
                self.status_changed.emit("Ready")

                async def send_audio() -> None:
                    nonlocal input_stream
                    was_recording = False
                    while not self._stopping.is_set():
                        recording = self._recording.is_set()
                        if recording and input_stream is None:
                            while not audio_queue.empty():
                                try:
                                    audio_queue.get_nowait()
                                except queue.Empty:
                                    break
                            input_stream = sd.RawInputStream(
                                samplerate=16000, channels=1, dtype="int16", blocksize=1600,
                                callback=microphone_callback, device=input_device,
                            )
                            input_stream.start()
                            self.status_changed.emit("Listening")
                        elif not recording and input_stream is not None:
                            input_stream.stop()
                            input_stream.close()
                            input_stream = None
                            while not audio_queue.empty():
                                try:
                                    audio_queue.get_nowait()
                                except queue.Empty:
                                    break
                            if was_recording:
                                await session.send_realtime_input(audio_stream_end=True)
                                self.status_changed.emit("Thinking")
                        if input_stream is not None:
                            try:
                                block = await asyncio.to_thread(audio_queue.get, True, 0.15)
                            except queue.Empty:
                                continue
                            if self._recording.is_set():
                                await session.send_realtime_input(
                                    audio=types.Blob(data=block, mime_type="audio/pcm;rate=16000")
                                )
                        else:
                            await asyncio.sleep(0.08)
                        was_recording = recording

                async def receive() -> None:
                    async for message in session.receive():
                        if self._stopping.is_set():
                            return
                        content = getattr(message, "server_content", None)
                        if content is None:
                            continue
                        user_transcription = getattr(content, "input_transcription", None)
                        if user_transcription and getattr(user_transcription, "text", None):
                            self.user_transcript.emit(user_transcription.text)
                        output_transcription = getattr(content, "output_transcription", None)
                        if output_transcription and getattr(output_transcription, "text", None):
                            self.assistant_transcript.emit(output_transcription.text)
                        model_turn = getattr(content, "model_turn", None)
                        if model_turn:
                            for part in model_turn.parts or []:
                                inline = getattr(part, "inline_data", None)
                                if inline and inline.data:
                                    audio = inline.data
                                    self.status_changed.emit("Speaking")
                                    for offset in range(0, len(audio), 480):
                                        block = audio[offset:offset + 480]
                                        output_stream.write(block)
                                        self.audio_level.emit(_amplitude(block))
                                        self.audio_advanced.emit(len(block) / 48000.0)
                        if getattr(content, "turn_complete", False):
                            self.turn_finished.emit()
                            self.status_changed.emit("Ready")

                sender_task = asyncio.create_task(send_audio())
                receiver_task = asyncio.create_task(receive())
                done, pending = await asyncio.wait({sender_task, receiver_task}, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for task in done:
                    task.result()
        finally:
            if input_stream is not None:
                _close_stream(input_stream)
            if output_stream is not None:
                _close_stream(output_stream)
            try:
                await client.aio.aclose()
            except Exception:
                pass


def _amplitude(raw: bytes) -> float:
    # The UI uses this only for an audio waveform; avatar articulation follows speech text.
    import numpy as np

    samples = np.frombuffer(raw, dtype=np.int16)
    return float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)) / 32768.0) if samples.size else 0.0


def _resolve_audio_device(sounddevice, selected: str | None, direction: str) -> int | None:
    if not selected:
        return None
    name, _, host = selected.partition("|||")
    for index, device in enumerate(sounddevice.query_devices()):
        host_name = sounddevice.query_hostapis(int(device["hostapi"]))["name"]
        channels = int(device["max_input_channels"] if direction == "input" else device["max_output_channels"])
        if channels > 0 and device["name"] == name and host_name == host:
            return index
    raise RuntimeError(f"Selected {direction} audio device is no longer available. Choose another in Settings.")


def _close_stream(stream) -> None:
    try:
        stream.stop()
    except Exception:
        pass
    try:
        stream.close()
    except Exception:
        pass


def _safe_error(exc: Exception) -> str:
    return redact_sensitive_text(str(exc))

