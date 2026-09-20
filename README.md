# Jarvis

A terminal browser agent powered by Groq. It can search the web, open pages,
read content, and interact with forms. Clicks, typing, and submissions require
confirmation. The selected browser remains visible.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
cp .env.example .env
```

Add your Groq key to `.env`:

```env
GROQ_API_KEY=your-key-here
JARVIS_MODEL=openai/gpt-oss-120b
```

`JARVIS_MODEL` is optional and defaults to `openai/gpt-oss-120b`. Keep `.env`
local; it is ignored by Git. Technical failures and tool audit events are
written to `jarvis.log`, which is also ignored.

Run Jarvis:

```bash
.venv/bin/python main.py
```

At startup, Jarvis asks whether you want Browser tasks, Desktop tasks, or Both.
Only Browser and Both modes ask whether to use Google Chrome or Brave. Browser
sessions are separate and do not attach to existing tabs or profiles.

Type `/quit` or `/exit` to stop Jarvis.
Type `/cancel` while a request is running to cancel it. The current network or
browser operation may finish first, then Jarvis stops before the next step.
Type `/voice` to record one voice request, review its transcription, and hear
Jarvis's reply. Risky-action confirmations still require terminal keyboard input.
Type `/undo` to reverse the most recent reversible navigation or field change.
Submitted forms and other external side effects cannot be undone.

## Memory and macros

Jarvis can remember user-requested preferences and task context locally:

- `remember_fact` stores a fact with a timestamp.
- `list_facts` displays remembered facts.
- `forget_fact` removes matching facts.
- `/memory clear` removes all facts after an explicit confirmation.

This data is stored in the local `memory.json` file. It is unencrypted and
Git-ignored, so it should not contain passwords, credentials, API keys, or
other secrets. The agent is instructed to refuse requests to remember secrets;
use memory only for preferences and task context.

Macros provide shortcuts for frequently repeated requests:

- `/macro save <name>` saves the previous typed request under a name.
- `/macro run <name>` runs a saved request.
- `/macro list` lists saved macros and previews.
- `/macro delete <name>` deletes a saved macro.

Running a macro replays the original request through the normal agent flow and
full confirmation checks every time. It is a shortcut for retyping a request,
not a way to skip safety checks or replay a recorded tool-call sequence.

## Voice mode (push-to-talk)

Type `/voice` to record one microphone request. Jarvis records until speech
ends or the recording limit is reached, transcribes the audio, prints the
transcription for review, sends that text through the normal agent flow, and
speaks the final reply aloud.

Voice mode is one-shot per command, not continuous or always-listening. Type
`/voice` again for the next voice turn. Confirmations for risky actions still
require keyboard input in the terminal: answer `y`/`yes` for ordinary actions
or type `SUBMIT` for form submissions. Spoken confirmations are not accepted.

Voice dependencies are included in `requirements.txt`:

```bash
.venv/bin/pip install sounddevice soundfile numpy
```

`sounddevice` uses PortAudio. On Linux, PortAudio may need to be installed
separately before installing or using the Python package, for example:

```bash
sudo apt install portaudio19-dev
```

Your operating system may also require microphone permission for the terminal
or Python process. If the audio dependencies are unavailable, `/voice` reports
the install command instead of raising an audio traceback.

Voice behavior can be configured in `.env`:

```env
# Speech-to-text model
JARVIS_STT_MODEL=whisper-large-v3

# Text-to-speech model and voice
JARVIS_TTS_MODEL=playai-tts
JARVIS_TTS_VOICE=Fritz-PlayAI
```

## Wake-word mode (experimental, opt-in)

Wake-word listening is off by default. Run `/wake-on` to start listening with
openWakeWord's standard pretrained `hey_jarvis` model for the phrase “hey
jarvis”; run `/wake-off` to stop it. The feature is experimental and opt-in.

Wake-word detection is fully local: microphone audio used for detection is
processed by openWakeWord on this machine and is not sent over the network.
Only the follow-up utterance recorded after a local wake-word detection is
sent to Groq for transcription, then processed through the normal agent flow.

Risky-action confirmations still require keyboard input in the terminal, even
in wake-word mode. This is intentional defense against a false-positive wake
trigger or a transcription mistake turning into an unconfirmed click, form
fill, or submission.

Saying the wake word again while Jarvis is speaking interrupts audio playback
(barge-in). It does not cancel an in-flight agent or tool operation; use
`/cancel` for that.

The `openwakeword` dependency is included in `requirements.txt`:

```bash
.venv/bin/pip install openwakeword
```

On first use, Jarvis calls `openwakeword.utils.download_models()` when the
standard model files are not already available. The small ONNX/TFLite files
are downloaded once and cached locally. Jarvis does not train or download a
custom wake-word model.

The model and detection sensitivity can be configured in `.env`:

```env
JARVIS_WAKEWORD_MODEL=hey_jarvis
JARVIS_WAKEWORD_THRESHOLD=0.5
```

Higher thresholds reduce false positives but can miss more spoken wake words;
lower thresholds are more sensitive but can produce more false positives.
`JARVIS_WAKEWORD_MODEL` may later point to a deliberately trained local
`.onnx` or `.tflite` model file.

## OS capabilities

In addition to screenshots and system-volume controls, Jarvis can read the
current text clipboard and write supplied text to the system clipboard.
Clipboard access is LOW risk operationally, but clipboard contents can be
sensitive. Clipboard text is redacted in audit logs and is never written in
full to `jarvis.log`.

Jarvis also provides these local OS capabilities:

- `open_application` launches only fixed, whitelist-based applications and
  requires confirmation. To add an application, edit `ALLOWED_APPS` in
  `config.py` deliberately with explicit argument lists for Windows, macOS,
  and Linux. Arbitrary paths and commands must not be accepted as tool input.
- `get_battery_status` and `get_system_status` are read-only and report battery
  state, CPU usage, memory usage, and available primary-drive space.
- `get_brightness` and `set_brightness` read and change screen brightness.
  Brightness changes are reversible and do not require confirmation; levels
  must be integers from 0 through 100.

Clipboard support uses `pyperclip`. System status uses `psutil`, and screen
brightness uses `screen-brightness-control`. They are included in
`requirements.txt`:

```text
pyperclip>=1.8.2
psutil>=5.9.0
screen-brightness-control>=0.24.2
```

To install these dependencies separately:

```bash
.venv/bin/pip install pyperclip psutil screen-brightness-control
```

Battery status reports no battery on desktop systems without one. Brightness
control has partial or no support on some macOS hardware and may report that
brightness control is unsupported for the display or operating system.

## Downloads

Browser downloads are saved automatically to the fixed project-local
`downloads/` directory (`DOWNLOAD_DIR`). The model cannot choose a custom save
path or filename. Downloads are limited to `MAX_DOWNLOAD_BYTES`, currently
100 MB; change that constant in `browser_executor.py` deliberately if a
different limit is needed.

If the suggested filename already exists, Jarvis preserves the existing file
and saves the new one with a numeric suffix such as `report_1.pdf`. After a
download, ask “what did you just download” and Jarvis can use
`get_last_download_info` to report the filename, saved path, and file size.

## Reliability features

- Startup configuration is validated before Jarvis starts. If multiple values
  are invalid, startup fails fast with a complete list of problems rather than
  reporting them one at a time as they are encountered.
- Groq rate-limit and quota failures receive a specific message explaining
  that the limit or quota was reached, separate from generic connection or
  transient API errors. Rate-limited requests receive only a small number of
  retries with their own backoff.
- If the browser crashes or is closed during use, Jarvis automatically
  relaunches the selected browser and retries the interrupted action exactly
  once. The new session has no previous page state: navigate and log in again,
  and do not reuse old `el_1`, `el_2`, etc. references. Undo history is also
  lost across browser recovery.

## Safety features

- URL validation rejects non-HTTP(S), local, private, loopback, and
  cloud-metadata addresses.
- Application launches use a fixed whitelist rather than model- or
  user-controlled commands and paths.
- Downloads use a fixed, non-model-controlled folder, collision-safe filenames,
  and a maximum file-size limit.

## Actions

- Search and open URLs
- Read page text
- List interactive elements
- Click, fill, and submit forms
- Go back
- Capture a desktop screenshot after confirmation
- Read and write the system clipboard

Interactive actions require confirmation.

## Limitations

Some sites use anti-bot or challenge pages that prevent automated access.
Jarvis now attempts to detect common bot-detection signals and clearly marks
likely blocks instead of silently presenting empty or misleading page content.
This is only a heuristic: it can produce false positives on legitimate short
pages and false negatives for challenge pages it does not recognize.

## Tests

Run the dependency-free test suite with:

```bash
.venv/bin/python -m unittest discover -s tests -v
```
