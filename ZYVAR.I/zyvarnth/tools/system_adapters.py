from __future__ import annotations

import platform
import re
import shutil
import subprocess


class SystemSettingsAdapter:
    """Platform-specific supported settings; commands are fixed and never invoke a shell."""

    def read_volume(self) -> int:
        system = platform.system()
        if system == "Darwin":
            raw = self._run(["osascript", "-e", "get volume settings"])
            match = re.search(r"output volume:(\d{1,3})", raw)
        elif system == "Linux":
            if shutil.which("pactl"):
                raw = self._run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
            elif shutil.which("amixer"):
                raw = self._run(["amixer", "get", "Master"])
            else:
                raise RuntimeError("Volume reading is unavailable: install pactl or amixer.")
            match = re.search(r"(?<!\d)(\d{1,3})%", raw)
        elif system == "Windows":
            try:
                from pycaw.pycaw import AudioUtilities
                endpoint = AudioUtilities.GetSpeakers().EndpointVolume
                return round(endpoint.GetMasterVolumeLevelScalar() * 100)
            except Exception as exc:
                raise RuntimeError("Windows volume control is unavailable; install the optional desktop adapter.") from exc
        else:
            raise RuntimeError(f"Volume control is unsupported on {system}.")
        if not match:
            raise RuntimeError("The OS did not report a readable volume percentage.")
        return int(match.group(1))

    def set_volume(self, percent: int) -> None:
        if not 0 <= percent <= 100:
            raise ValueError("Volume must be between 0 and 100 percent.")
        system = platform.system()
        if system == "Darwin":
            self._run(["osascript", "-e", f"set volume output volume {percent}"])
        elif system == "Linux":
            if shutil.which("pactl"):
                self._run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"])
            elif shutil.which("amixer"):
                self._run(["amixer", "-q", "sset", "Master", f"{percent}%"])
            else:
                raise RuntimeError("Volume control is unavailable: install pactl or amixer.")
        elif system == "Windows":
            try:
                from pycaw.pycaw import AudioUtilities
                endpoint = AudioUtilities.GetSpeakers().EndpointVolume
                endpoint.SetMasterVolumeLevelScalar(percent / 100, None)
            except Exception as exc:
                raise RuntimeError("Windows volume control is unavailable; install the optional desktop adapter.") from exc
        else:
            raise RuntimeError(f"Volume control is unsupported on {system}.")

    @staticmethod
    def _run(command: list[str]) -> str:
        if shutil.which(command[0]) is None:
            raise RuntimeError(f"Required system command is unavailable: {command[0]}.")
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=8)
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "command failed").splitlines()[0][:180]
            raise RuntimeError(f"System setting command failed: {detail}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("System setting command timed out.") from exc
        return result.stdout.strip()

