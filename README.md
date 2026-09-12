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
Type `/undo` to reverse the most recent reversible navigation or field change.
Submitted forms and other external side effects cannot be undone.

## Actions

- Search and open URLs
- Read page text
- List interactive elements
- Click, fill, and submit forms
- Go back
- Capture a desktop screenshot after confirmation

Interactive actions require confirmation.

## Tests

Run the dependency-free test suite with:

```bash
.venv/bin/python -m unittest discover -s tests -v
```
