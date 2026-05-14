"""
╔══════════════════════════════════════════════════════════════════════════╗
║  CUSTOMIZATION POINT  ·  orchestration.py                                ║
║                                                                          ║
║  The Gemini Live session loop. Three concurrent tasks per session:       ║
║                                                                          ║
║       send_audio    →  mic → session.send_realtime_input(...)            ║
║       send_text     →  stdin → session.send_client_content(...)          ║
║       receive_loop  →  session.receive() → speaker / hooks / tool calls  ║
║                                                                          ║
║  Hook insertion points are flagged with ▶▶▶  comments. If you want a     ║
║  new behavior at a specific point in the turn, the right answer is       ║
║  almost always a hook in guardrails.py, not edits here.                  ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator
from typing import Any

from google import genai
from google.genai import types

import config
import guardrails
import intent_router
from prompts import SYSTEM_PROMPT
from observability import log_event, log_tool_call, log_tool_result
from tools import (
    Session, dispatch, function_declarations, list_tool_names,
)


def _put_debug(
    q: asyncio.Queue[dict[str, Any]] | None, payload: dict[str, Any],
) -> None:
    if q is None:
        return
    try:
        q.put_nowait(payload)
    except asyncio.QueueFull:
        pass


def _jsonish(value: Any) -> Any:
    """Best-effort JSON-serializable value for debug payloads."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _session_memory_hint(session: Session) -> str | None:
    """Short system addendum so the model does not re-ask for stored facts."""
    parts: list[str] = []
    if session.verified_email and session.verified_customer_id:
        parts.append(
            "Customer is already verified for this browser session: "
            f"email {session.verified_email}, "
            f"internal customer_id {session.verified_customer_id}. "
            "Do not ask for their email or to look up their account again "
            "unless they say they are a different customer or account."
        )
    if session.last_order_id:
        parts.append(
            f"Last order referenced in this browser session: {session.last_order_id}."
        )
    if session.escalated:
        parts.append(
            "An escalation was already opened in this browser session."
        )
    if not parts:
        return None
    return (
        "Browser session memory (trust for continuity; user may correct):\n"
        + "\n".join(parts)
    )


def _put_session_state(
    q: asyncio.Queue[dict[str, Any]] | None, session: Session,
) -> None:
    if q is None:
        return
    payload = {
        "type": "session_state",
        "memory": session.memory_snapshot(),
    }
    try:
        q.put_nowait(payload)
    except asyncio.QueueFull:
        pass


async def _drain_web_memory_restore(
    agent: BooklyLiveAgent,
    restore_q: asyncio.Queue[dict[str, Any]] | None,
) -> None:
    """Apply at most one queued client memory snapshot before Live connect."""
    if restore_q is None:
        return
    snap: dict[str, Any] | None = None
    try:
        snap = restore_q.get_nowait()
    except asyncio.QueueEmpty:
        pass
    if snap is None:
        try:
            snap = await asyncio.wait_for(restore_q.get(), timeout=0.6)
        except asyncio.TimeoutError:
            return
    if snap:
        agent.session.apply_memory_snapshot(snap)


# ────────────────────────────────────────────────────────────────────────── #
#  Build the Gemini Live config once.                                       #
# ────────────────────────────────────────────────────────────────────────── #
def _build_live_config(
    response_modality: str,
    *,
    memory_hint: str | None = None,
) -> types.LiveConnectConfig:
    """`response_modality` is "AUDIO" or "TEXT". Both share the same
    system prompt, tools, and safety knobs — only the output channel
    differs. Optional ``memory_hint`` adds a second system part for
    restored browser session context (web voice)."""

    declarations = [
        types.FunctionDeclaration(**fd) for fd in function_declarations()
    ]

    speech_config = types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name=config.VOICE,
            )
        )
    )

    parts: list[types.Part] = [types.Part(text=SYSTEM_PROMPT)]
    if memory_hint:
        parts.append(types.Part(text=memory_hint))

    return types.LiveConnectConfig(
        response_modalities=[response_modality],
        system_instruction=types.Content(parts=parts),
        tools=[types.Tool(function_declarations=declarations)],
        speech_config=speech_config if response_modality == "AUDIO" else None,
    )


# ────────────────────────────────────────────────────────────────────────── #
#  Session manager                                                          #
# ────────────────────────────────────────────────────────────────────────── #
class BooklyLiveAgent:
    """Holds the per-conversation Session plus the wired-up event loop.

    The class is thin on purpose. Most behavior lives in:
      - prompts.py        (what the model knows)
      - tools/*           (what the model can do)
      - guardrails.py     (what gets blocked/transformed)
      - config.py         (knobs)
    """

    def __init__(self, *, modality: str = "AUDIO") -> None:
        if not config.API_KEY:
            raise RuntimeError(
                "GOOGLE_API_KEY (or GEMINI_API_KEY) is not set."
            )
        self.client = genai.Client(
            api_key=config.API_KEY,
            http_options={"api_version": config.API_VERSION},
        )
        self.modality = modality  # "AUDIO" or "TEXT"
        self.session = Session()
        log_event("session_open", tools=list_tool_names(), modality=modality)

    # ────────────────────────────────────────────────────────────── #
    #  Public: text mode (one turn at a time, no audio streaming)
    # ────────────────────────────────────────────────────────────── #
    async def run_text(self) -> None:
        cfg = _build_live_config("TEXT")
        async with self.client.aio.live.connect(
            model=config.MODEL, config=cfg
        ) as live:
            while True:
                try:
                    user = await asyncio.get_event_loop().run_in_executor(
                        None, input, "\nYou: "
                    )
                except (EOFError, KeyboardInterrupt):
                    return
                user = (user or "").strip()
                if not user:
                    continue
                if user.lower() in {"quit", "exit", ":q"}:
                    return

                # ▶▶▶ Hook: pre_user_text
                d = guardrails.pre_user_text(self.session, user)
                if not d.allow:
                    log_event("guardrail_block", phase="pre_user_text", reason=d.reason)
                    print(f"\nAgent: {d.speak_instead}\n")
                    continue

                # ▶▶▶ Optional: intent router
                if intent_router.ENABLED:
                    intent = intent_router.classify(d.payload)
                    log_event("intent", value=intent.value)

                await live.send_client_content(
                    turns=types.Content(
                        role="user",
                        parts=[types.Part(text=d.payload)],
                    ),
                    turn_complete=True,
                )
                await self._consume_turn(live, print_text=True)

    # ────────────────────────────────────────────────────────────── #
    #  Public: voice mode (real-time bidi audio)
    # ────────────────────────────────────────────────────────────── #
    async def run_voice(self) -> None:
        from voice_io import MicCapture, Speaker  # local import keeps text
                                                  # mode free of audio deps

        mic = MicCapture()
        speaker = Speaker()
        try:
            await self.run_voice_with_streams(
                mic.frames(), speaker, text_out=None,
            )
        finally:
            mic.close()
            speaker.close()

    async def run_voice_with_streams(
        self,
        mic_frames: AsyncIterator[bytes],
        speaker: Any,
        *,
        text_out: asyncio.Queue[str] | None = None,
        debug_out: asyncio.Queue[dict[str, Any]] | None = None,
        session_out: asyncio.Queue[dict[str, Any]] | None = None,
        restore_q: asyncio.Queue[dict[str, Any]] | None = None,
    ) -> None:
        """Drive the same Live AUDIO session as :meth:`run_voice`, but read
        PCM input from ``mic_frames`` and play output through ``speaker``
        (anything with a synchronous ``write(bytes)`` method — e.g.
        :class:`voice_io.Speaker` or a queue-backed bridge for the web UI).
        Optional ``text_out`` receives assistant text chunks (transcript /
        captions) when the model sends text alongside audio.
        Optional ``debug_out`` receives structured tool-call / tool-response
        events for developer UIs (e.g. the browser debug panel).
        Optional ``session_out`` pushes ``session_state`` after tool batches
        so the browser can persist :class:`~tools.Session` fields.
        Optional ``restore_q`` receives at most one client memory snapshot
        before connecting to Live (web voice)."""

        await _drain_web_memory_restore(self, restore_q)
        _put_session_state(session_out, self.session)
        hint = _session_memory_hint(self.session)
        cfg = _build_live_config("AUDIO", memory_hint=hint)
        async with self.client.aio.live.connect(
            model=config.MODEL, config=cfg
        ) as live:

            async def stream_mic() -> None:
                async for chunk in mic_frames:
                    await live.send_realtime_input(
                        audio=types.Blob(
                            data=chunk, mime_type=config.INPUT_MIME,
                        )
                    )

            async def receive() -> None:
                await self._consume_turn(
                    live,
                    speaker=speaker,
                    loop=True,
                    text_out=text_out,
                    debug_out=debug_out,
                    session_out=session_out,
                )

            mic_task = asyncio.create_task(stream_mic())
            recv_task = asyncio.create_task(receive())
            try:
                done, pending = await asyncio.wait(
                    {mic_task, recv_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                for t in done:
                    if t.cancelled():
                        continue
                    exc = t.exception()
                    if exc is not None:
                        raise exc
            except KeyboardInterrupt:
                mic_task.cancel()
                recv_task.cancel()
                await asyncio.gather(
                    mic_task, recv_task, return_exceptions=True,
                )
                return

    # ────────────────────────────────────────────────────────────── #
    #  Inner loop — consume one or many model turns
    # ────────────────────────────────────────────────────────────── #
    async def _consume_turn(
        self, live, *, print_text: bool = False,
        speaker=None, loop: bool = False,
        text_out: asyncio.Queue[str] | None = None,
        debug_out: asyncio.Queue[dict[str, Any]] | None = None,
        session_out: asyncio.Queue[dict[str, Any]] | None = None,
    ) -> None:
        # Count only tool-call *batches* from the server. Do not count every
        # `live.receive()` message: AUDIO mode streams many small chunks per
        # reply; treating those like iterations trips the cap mid-utterance,
        # stops reading the socket, and the connection dies (keepalive ping
        # timeout while the mic task still runs).
        tool_iters = 0
        async for response in live.receive():
            # ── tool calls ─────────────────────────────────────── #
            if response.tool_call:
                tool_iters += 1
                if tool_iters > config.MAX_TOOL_ITERS_PER_TURN:
                    log_event("iter_cap_hit", tool_iters=tool_iters)
                    break
                await self._handle_tool_call(
                    live,
                    response.tool_call,
                    debug_out=debug_out,
                    session_out=session_out,
                )
                continue

            sc = getattr(response, "server_content", None)
            if not sc:
                continue

            # ── audio / text from the model ─────────────────────── #
            model_turn = getattr(sc, "model_turn", None)
            if model_turn:
                for part in model_turn.parts:
                    if part.inline_data and speaker is not None:
                        # PCM audio chunk — stream straight to the speaker
                        speaker.write(part.inline_data.data)
                    if part.text:
                        # ▶▶▶ Hook: pre_agent_response (text mode)
                        d = guardrails.pre_agent_response(
                            self.session, part.text,
                        )
                        out = d.speak_instead if not d.allow else d.payload
                        if not d.allow:
                            log_event("guardrail_block",
                                      phase="pre_agent_response",
                                      reason=d.reason)
                        if print_text:
                            print(f"\nAgent: {out}")
                        if text_out is not None:
                            try:
                                text_out.put_nowait(out)
                            except asyncio.QueueFull:
                                pass

            # End-of-turn marker — model is done speaking for now.
            if getattr(sc, "turn_complete", False):
                tool_iters = 0
                if not loop:
                    return

    # ────────────────────────────────────────────────────────────── #
    #  Tool-call handler
    # ────────────────────────────────────────────────────────────── #
    async def _handle_tool_call(
        self, live, tool_call: Any,
        *,
        debug_out: asyncio.Queue[dict[str, Any]] | None = None,
        session_out: asyncio.Queue[dict[str, Any]] | None = None,
    ) -> None:
        responses: list[types.FunctionResponse] = []
        for fc in tool_call.function_calls:
            args = dict(fc.args or {})

            # ▶▶▶ Hook: pre_tool_call
            d = guardrails.pre_tool_call(self.session, fc.name, args)
            if not d.allow:
                log_event("guardrail_block",
                          phase="pre_tool_call",
                          tool=fc.name, reason=d.reason)
                blocked_out = json.dumps({
                    "ok": False, "error_code": "blocked_by_policy",
                    "message": d.speak_instead or "Tool blocked.",
                })
                _put_debug(debug_out, {
                    "type": "debug",
                    "kind": "tool_call",
                    "name": fc.name,
                    "args": args,
                    "blocked": True,
                    "reason": d.reason,
                })
                _put_debug(debug_out, {
                    "type": "debug",
                    "kind": "tool_response",
                    "name": fc.name,
                    "output": json.loads(blocked_out),
                })
                responses.append(types.FunctionResponse(
                    id=fc.id, name=fc.name,
                    response={"output": blocked_out},
                ))
                continue

            log_tool_call(fc.name, args)
            _put_debug(debug_out, {
                "type": "debug",
                "kind": "tool_call",
                "name": fc.name,
                "args": args,
            })
            raw = dispatch(self.session, fc.name, d.payload or args)

            # ▶▶▶ Hook: post_tool_call
            d2 = guardrails.post_tool_call(
                self.session, fc.name, args, raw,
            )
            scrubbed = d2.payload if d2.allow else raw
            log_tool_result(fc.name, scrubbed)

            _put_debug(debug_out, {
                "type": "debug",
                "kind": "tool_response",
                "name": fc.name,
                "output": _jsonish(scrubbed),
            })

            responses.append(types.FunctionResponse(
                id=fc.id, name=fc.name,
                response={"output": scrubbed},
            ))

        await live.send_tool_response(function_responses=responses)
        _put_session_state(session_out, self.session)
