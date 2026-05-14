# Bookly — Gemini Live Support Agent

A voice/chat customer-support agent for the fictional Bookly bookstore,
built on the **Gemini Live API** via Google's `google-genai` SDK.

The codebase is laid out to be **customized**, not just read. Every file
that's meant to be a knob has a banner at the top calling out the
customization surface. Start with `config.py`, then `prompts.py`, then
`tools/`, then `guardrails.py`.

## Layout

```
bookly-gemini/
├── main.py              # CLI entry — --text (default), --voice, or --web
├── web_server.py        # FastAPI + WebSocket bridge for browser voice UI
├── web/                 # Static assets (index.html, app.js, styles.css)
├── orchestration.py     # Gemini Live session loop (the only file that
│                        # talks to the API). Hook insertion points are
│                        # marked ▶▶▶.
│
├── config.py            # 📌 CUSTOMIZATION: model, voice, policy
│                        #     thresholds, observability toggles
├── prompts.py           # 📌 CUSTOMIZATION: persona, rules, tone, format
├── tools/               # 📌 CUSTOMIZATION: add a file + @tool to add a
│   ├── __init__.py      #     capability. The registry handles the rest.
│   ├── _registry.py
│   ├── orders.py
│   ├── returns.py
│   ├── help_center.py
│   └── escalation.py
├── guardrails.py        # 📌 CUSTOMIZATION: four hooks called at fixed
│                        #     points in every turn
├── intent_router.py     # 📌 CUSTOMIZATION: optional pre-LLM router
├── observability.py     # 📌 CUSTOMIZATION: swap _emit() for your sink
│
├── voice_io.py          # Mic + speaker (PCM streams)
├── data.py              # Mock backend
├── test_smoke.py        # Offline tests for tools + guardrails
└── requirements.txt
```

## Setup

```bash
pip install -r requirements.txt
export GOOGLE_API_KEY=...      # or GEMINI_API_KEY

# macOS voice mode also needs:
brew install portaudio
```

## Run

```bash
python main.py            # text chat
python main.py --voice    # bidirectional Gemini Live audio (CLI mic/speaker)
python main.py --web      # same Live session in the browser (http://127.0.0.1:8765/)
python test_smoke.py      # offline tests (no API key needed)
```

For `--web`, set `BOOKLY_WEB_HOST` / `BOOKLY_WEB_PORT` if you need a different bind address. Use Chrome or Edge and allow microphone access when prompted.

## Customization map

If you want to change…              | Edit
------------------------------------|----------------------------
the model or voice                  | `config.py` → `MODEL`, `VOICE`
how long the return window is       | `config.py` → `RETURN_WINDOW_DAYS`
the agent's tone or rules           | `prompts.py` → `RULES` / `TONE`
add a new capability (e.g. cancel)  | new file in `tools/`, decorate with `@tool(...)`
block destructive tools temporarily | `guardrails.py` → `READ_ONLY_MODE = True`
catch prompt-injection patterns     | `guardrails.py` → `PROMPT_INJECTION_PATTERNS`
filter the agent's responses        | `guardrails.py` → `pre_agent_response`
ship events to Datadog/OTLP         | `observability.py` → `_emit`
route by intent before the LLM      | `intent_router.py` → `ENABLED = True`

## Hook execution order (per user turn)

```
   user audio / text
        │
        ▼
   pre_user_text         ◀── guardrails.py
        │
        ▼
   (optional) intent_router.classify(...)
        │
        ▼
   Gemini Live  ─────────────────────────┐
        │                                │
        ▼                                │
   tool_call?  ─yes─►  pre_tool_call ────┤
        │                  │             │
        │                  ▼             │
        │              dispatch()        │
        │                  │             │
        │                  ▼             │
        │            post_tool_call      │
        │                  │             │
        │                  └─────────────┤
        ▼                                │
   audio / text reply ◀───────────────── ┘
        │
        ▼
   pre_agent_response    ◀── guardrails.py
        │
        ▼
   speaker / stdout
```

## Why Gemini Live (vs Whisper → LLM → TTS)

- **Native bidirectional audio** — input and output stream as PCM in
  a single WebSocket. No STT/TTS plumbing, no per-turn round-trip.
- **Tool calling first-class** — the function-call protocol on Live is
  identical to standard Gemini; you can copy declarations between modes.
- **VAD built in** — the API handles end-of-turn detection, so we don't
  need a push-to-talk button.

What we still build ourselves: the **orchestration shape** (so we can
insert guardrail hooks at the right points), the **tool registry** (so
adding capabilities is one file), and the **policy enforcement** (so the
model can't bypass a rule by being clever in prose).

## Required behaviors demonstrated

| Required behavior             | Where it shows up |
|-------------------------------|-------------------|
| Multi-turn interaction        | Return flow: order → eligibility → confirmation → RMA |
| Tool use                      | 5 tools registered; see `tools/` |
| Clarifying question           | "I have a problem with my order" → asks for order ID + email instead of guessing |
| Identity verification         | Order data refused until `verify_customer` succeeds — enforced server-side |
| Policy refusal                | 45-day-old return rejected by `get_return_eligibility` |
| Guardrail enforcement         | Prompt-injection patterns blocked in `pre_user_text`; forbidden claims blocked in `pre_agent_response` |
| Graceful escalation           | `escalate_to_human` with summary; auto-trigger after 2 failed turns |

## Assumptions documented

1. Auth is mocked. Production would attach a JWT/session at the app
   layer; the prototype asks for the email on file.
2. Knowledge base is keyword scoring over five hand-written articles.
   Production replaces `search_help_center` with a vector retriever.
3. Single-session memory only. `Session` dies with the process.
4. The Gemini Live model name in `config.py` (`gemini-2.0-flash-live-001`)
   is current as of this writing; the preview "native-audio-dialog"
   variant is available via env override.
