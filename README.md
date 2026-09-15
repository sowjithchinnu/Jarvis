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

## Actions

- Search and open URLs
- Read page text
- List interactive elements
- Click, fill, and submit forms
- Go back
- Capture a desktop screenshot after confirmation
- Read and write the system clipboard

Interactive actions require confirmation.

## Tests

Run the dependency-free test suite with:

```bash
.venv/bin/python -m unittest discover -s tests -v
```
