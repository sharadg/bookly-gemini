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
├── identity_cache.py    # Server-side verify_customer result (hydrates new
│                        #     Live sessions in-process; not client-writable)
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
# Optional: put the same keys in a project-root .env — config.py loads it
# automatically via python-dotenv.

# macOS voice mode also needs:
brew install portaudio
```

### Environment overrides (optional)

| Variable | Purpose |
|----------|---------|
| `BOOKLY_MODEL` | Gemini Live model id (default in `config.py` is `gemini-3.1-flash-live-preview`) |
| `BOOKLY_VOICE` | Live voice name (e.g. `Zephyr`) |
| `BOOKLY_WEB_HOST` / `BOOKLY_WEB_PORT` | Bind address for `--web` (defaults `127.0.0.1` / `8765`) |
| `BOOKLY_TRANSCRIPT` | Path for JSONL session log from `observability._emit` (default `session.jsonl`; empty disables) |

## Run

```bash
python main.py            # text chat
python main.py --voice    # bidirectional Gemini Live audio (CLI mic/speaker)
python main.py --web      # same Live session in the browser (http://127.0.0.1:8765/)
python test_smoke.py      # offline tests (no API key needed)
```

For `--web`, set `BOOKLY_WEB_HOST` / `BOOKLY_WEB_PORT` if you need a different bind address. Use Chrome or Edge and allow microphone access when prompted. The page includes a **debug log** of tool calls and responses (streamed from the server over the same WebSocket).

After a successful `verify_customer`, the server keeps a **short-lived identity cache** (`identity_cache.py`): a new browser tab or refresh opens a fresh Gemini Live session, but the customer does not have to re-verify until the Python process restarts (demo scope; production would use an opaque token).

## Customization map

If you want to change…              | Edit
------------------------------------|----------------------------
the model or voice                  | `config.py` → `MODEL`, `VOICE` (or `BOOKLY_MODEL` / `BOOKLY_VOICE`)
how long the return window is       | `config.py` → `RETURN_WINDOW_DAYS`
the agent's tone or rules           | `prompts.py` → `RULES` / `TONE`
add a new capability (e.g. cancel)  | new file in `tools/`, decorate with `@tool(...)`
block destructive tools temporarily | `guardrails.py` → `READ_ONLY_MODE = True`
catch prompt-injection patterns     | `guardrails.py` → `PROMPT_INJECTION_PATTERNS`
filter the agent's responses        | `guardrails.py` → `pre_agent_response`
ship events to Datadog/OTLP         | `observability.py` → `_emit`
route by intent before the LLM      | `intent_router.py` → `ENABLED = True`
how post-verify identity persists   | `identity_cache.py` (in-process demo; replace with token store in prod)

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
| Identity verification         | Order data refused until `verify_customer` succeeds — enforced server-side; same process reuses verification via `identity_cache` |
| Policy refusal                | 45-day-old return rejected by `get_return_eligibility` |
| Guardrail enforcement         | Prompt-injection patterns blocked in `pre_user_text`; forbidden claims blocked in `pre_agent_response` |
| Graceful escalation           | `escalate_to_human` with summary; auto-trigger after 2 failed turns |

## Assumptions documented

1. Auth is mocked. Production would attach a JWT/session at the app
   layer; the prototype asks for the email on file.
2. Knowledge base is keyword scoring over five hand-written articles.
   Production replaces `search_help_center` with a vector retriever.
3. Each WebSocket / CLI run opens a new Gemini Live session (no client-side
   transcript replay). The in-process `Session` object and Live context end
   when that connection ends. Verified identity can still **hydrate** into a
   new session from `identity_cache` until the server exits. Optional JSONL
   transcript: `BOOKLY_TRANSCRIPT` / `config.TRANSCRIPT_PATH`.
4. Default Live model is `gemini-3.1-flash-live-preview` in `config.py`;
   override with `BOOKLY_MODEL` (e.g. `gemini-2.0-flash-live-001` or preview
   native-audio ids when your account supports them).
