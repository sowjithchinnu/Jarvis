# Jarvis

A terminal browser agent powered by Groq. It can search the web, open pages,
read content, and interact with forms. Clicks, typing, and submissions require
confirmation. The controlled Chromium browser remains visible.

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

At startup, Jarvis asks whether to use Google Chrome or Brave. It opens a
separate browser session and does not attach to your existing tabs or profiles.

Type `/quit` or `/exit` to stop Jarvis.
Type `/undo` to reverse the most recent reversible navigation or field change.
Submitted forms and other external side effects cannot be undone.

## Actions

- Search and open URLs
- Read page text
- List interactive elements
- Click, fill, and submit forms
- Go back

Interactive actions require confirmation.

Drawing strokes generated as one drawing are grouped into a single confirmation
so Jarvis does not interrupt once for every stroke.

## Tests

Run the dependency-free test suite with:

```bash
.venv/bin/python -m unittest discover -s tests -v
```
