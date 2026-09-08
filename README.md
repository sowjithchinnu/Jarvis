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
```

Run Jarvis:

```bash
.venv/bin/python main.py
```

The terminal displays the conversation while a visible Chromium browser opens
alongside it.

Type `/quit` or `/exit` to stop Jarvis.

## Actions

- Search and open URLs
- Read page text
- List interactive elements
- Click, fill, and submit forms
- Go back

Interactive actions require confirmation.
