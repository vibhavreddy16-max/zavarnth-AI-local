# Zyvarnth

Zyvarnth is an original PyQt6 personal AI desktop assistant with streaming Gemini chat, explicit push-to-talk voice, local approved memory, live research, a validated action layer, and a persistent undo journal. It uses the Mark-LV repository as a capability reference and has its own interface, module structure, and implementation.

## Requirements

- Python 3.11, 3.12, or 3.13
- macOS, Windows, or Linux with a graphical desktop session
- A Google Gemini API key for chat, voice, and AI task planning
- Microphone permission for push-to-talk voice
- Screen-recording permission for requested screenshot analysis

## Install and run

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[desktop,notify]'
.venv/bin/python -m playwright install chromium
.venv/bin/python main.py
```

Or run `./install.sh` after making it executable. The script accepts `PYTHON_BIN` when the supported interpreter is not named `python3`.
On Windows, run `Set-ExecutionPolicy -Scope Process Bypass` if needed, then `./install.ps1`; it also accepts `PYTHON_BIN`.

Open **Settings & permissions**, paste a Gemini API key, and save it to the operating system credential store. The key is never shown again. `GEMINI_API_KEY` is also read from the process environment; a local `.env` file is supported and ignored by Git. See [.env.example](.env.example).

## What works

- **Conversation:** real Gemini streaming responses, stored conversation sessions, request cancellation, and optional screenshot input. No placeholder model replies are generated.
- **Live voice:** Gemini Live audio, selectable built-in voice and microphone/speaker devices, speech transcriptions, audio playback, and push-to-talk. The input stream is opened only while the push-to-talk control is held. The Ctrl+Space shortcut is scoped to the Zyvarnth window.
- **Task agent:** Gemini proposes a short plan from a fixed tool catalog. Every step is schema-checked; file writes/moves/deletes, desktop typing/shortcuts, and browser interaction require a human confirmation dialog. Pause, resume, and cancel are available.
- **Research:** current DuckDuckGo results with source URLs and snippets; the task agent can write a Gemini summary with numbered source links. Weather uses Open-Meteo geocoding and forecast data.
- **Files and desktop:** file search/read is limited to folders the user approved. UTF-8 text, PDF, and DOCX files can be read; a requested document summary sends bounded extracted text to the configured Gemini API. Text writes, moves, and recoverable deletes have guarded undo. The tool layer has no general shell command.
- **Browser:** Playwright visits pages and extracts visible text. One-shot form fill and click actions use an isolated browser context and always require approval. They do not reuse the user's signed-in browser profile.
- **Screen awareness:** screenshot capture begins only after the user presses Analyze Screen. Capture success or failure is shown; the image is sent to Gemini only after successful capture.
- **Memory:** separate SQLite facts are user-entered or edited in Memory Manager. Prompt retrieval uses relevant matches instead of dumping the full memory store. Memory can be disabled or erased without deleting chat history.
- **Monitoring and reminders:** CPU, RAM, disk, battery, and temperature are read where the OS exposes them. Reminders are stored locally and fire in-app; the optional `notify` extra also attempts an OS notification. Volume adjustment is available only where a platform adapter can read the current value and therefore undo safely.
- **Plugins:** local Python plugin modules return validated `ToolSpec` declarations and share the same executor and per-tool confirmation checks. Plugins are disabled unless explicitly enabled in Settings; enabling one means trusting its code. See [plugins/README.md](plugins/README.md) and the inert clock example.

## Security and data

Settings and the SQLite database live in the per-user directories selected by `platformdirs`. The Gemini credential is stored with `keyring` when available. Conversation history and long-term memory use separate tables. Activity records omit file contents and only keep bounded backups for supported undo operations.

File paths are resolved against approved roots, tool arguments are type-checked, writes are limited to 1 MB, and undo verifies file hashes before restoring anything. Undo refuses to overwrite later edits. The system never executes model-written shell commands. The application does not expose message sending, software installation, power controls, or other unavailable actions as if they succeeded.

## Architecture

```text
zyvarnth/
  ai.py                 Gemini text streaming, task planning, research summaries
  audio/live.py         Gemini Live audio capture/playback worker
  config.py             user settings and keychain access
  database.py           SQLite sessions, memories, actions, reminders
  memory.py             approved facts and relevance retrieval
  monitoring.py         background hardware telemetry
  plugins.py            explicit local plugin discovery
  screen.py             requested screenshot capture
  task_agent.py         plan validation, approval, pause/resume/cancel
  tools/                validators, Playwright, OS adapters, journal and undo
  ui/                   PyQt6 panels, holographic avatar, workers, styling
tests/                   storage, permission, URL and undo regression tests
```

## Current limits

- A Gemini key is needed for real chat, voice, task planning, and AI summaries. The app displays a configuration error instead of generating a simulated reply. No API key was available in the development environment, so a real Gemini network session was not exercised.
- Live voice uses push-to-talk; wake-word capture and continuous listening are not implemented. Voice state, speech text, and audio are shown while a Live session is connected. Avatar mouth movement uses transcript visemes advanced by actual output-audio duration; it is an approximation, not formant-level lip sync.
- Playwright uses a fresh isolated context per action; it does not control existing signed-in browser tabs or preserve cookies between actions.
- Computer control covers a fixed application allowlist, approved-folder file operations, explicit typing/shortcuts, supported volume changes, reminders, and browser actions. Brightness, Wi-Fi, shutdown/restart, outbound messages, software installation, and webcam capture are not exposed.
- Screenshot analysis depends on OS screen-capture permission. The feature was not exercised during automated checks because it would capture the developer's actual screen.
- The app and adapters were exercised on macOS only. Windows and Linux compatibility still needs hands-on platform testing, especially microphone/sample-rate behavior, desktop automation permissions, and OS notifications.

## Troubleshooting

- **No Gemini connection:** check Settings for the credential status and confirm the selected model is enabled for the key. API errors are surfaced in the app; model aliases may change over time.
- **Microphone is unavailable:** allow microphone access for the terminal or packaged app in OS privacy settings. On Linux, confirm a PortAudio-compatible input device is available. The app listens only while push-to-talk is held.
- **No voice output:** check the system output device and ensure the Live model supports the selected voice. Voice session errors are shown in the conversation panel.
- **Playwright cannot launch Chromium:** run `.venv/bin/python -m playwright install chromium`. The browser tool reports installation or navigation failures rather than substituting fake content.
- **macOS screen capture fails:** grant Screen & System Audio Recording / Screen Recording permission to the app host and restart it. No screenshot is submitted when capture fails.
- **Linux desktop shortcut/type support:** install the optional desktop extra and run in a graphical X11/Wayland session. Some desktop environments deny automation APIs.
- **Temperature is unavailable:** many Macs and virtual machines do not expose temperature through psutil; the UI leaves this metric unavailable rather than estimating it.
- **Undo is unavailable:** irreversible actions and actions whose file contents changed after execution are marked unavailable or refused to protect later edits.

## Verification

```sh
.venv/bin/python -m pytest
```

The application has been developed and locally verified on macOS. Windows and Linux adapters are included, but must still be exercised on those operating systems to claim platform certification.

