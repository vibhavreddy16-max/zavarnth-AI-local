# Zyvarnth troubleshooting

| Symptom | Check |
| --- | --- |
| Gemini reports no key | Save the key in Settings, or set `GEMINI_API_KEY` before starting the app. The key itself is never printed. |
| Model not found or access denied | Change the text/live model in Settings to a model enabled for your Google API project. |
| Microphone open fails | Grant OS microphone permission, select a working system input, and check that no exclusive-mode app owns it. Capture starts only during push-to-talk. |
| Audio is choppy | Check that the selected default input/output devices support 16 kHz input and 24 kHz output through PortAudio; reconnect Live Voice after changing devices. |
| Screenshot capture denied | Grant screen-recording permission to the app host, restart Zyvarnth, and press Analyze Screen again. The application reports failure without claiming it saw the screen. |
| Browser launch fails | Install the Playwright Chromium browser using `python -m playwright install chromium`. Authenticated browser profiles are intentionally not copied into the automation context. |
| File not found by tools | Add the file's containing folder in Settings → Approved File Roots. Symlink-resolved paths outside approved folders are rejected. |
| Undo refuses | The target may have changed since Zyvarnth's action or the original path may now be occupied. Review the Activity entry and restore manually if needed. |
| Keychain backend unavailable | Use `GEMINI_API_KEY` in the launching process environment. Zyvarnth does not silently write a key to plaintext settings. |

