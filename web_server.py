"""
Local web UI for Bookly voice — bridges the browser to Gemini Live over
WebSocket. The API key stays on the server.

Run:
    uvicorn web_server:app --host 127.0.0.1 --port 8765
    # or:  python main.py --web

Then open http://127.0.0.1:8765/ (use the URL printed by uvicorn if you
change host/port). Chrome or Edge recommended for Web Audio.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from orchestration import BooklyLiveAgent
from prompts import OPENING_GREETING

WEB_ROOT = Path(__file__).resolve().parent / "web"

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(WEB_ROOT)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


class _QueuePCMSpeaker:
    """Sync ``write(bytes)`` used by orchestration; forwards to an asyncio queue."""

    __slots__ = ("_q",)

    def __init__(self, q: asyncio.Queue[bytes | None]) -> None:
        self._q = q

    def write(self, pcm: bytes) -> None:
        try:
            self._q.put_nowait(pcm)
        except asyncio.QueueFull:
            pass


async def _queue_mic_iter(
    in_q: asyncio.Queue[bytes | None],
) -> AsyncIterator[bytes]:
    while True:
        chunk = await in_q.get()
        if chunk is None:
            break
        yield chunk


@app.websocket("/ws/voice")
async def voice_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json(
        {"type": "greeting", "text": OPENING_GREETING},
    )

    in_q: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=128)
    pcm_q: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=256)
    text_out: asyncio.Queue[str] = asyncio.Queue(maxsize=64)
    speaker = _QueuePCMSpeaker(pcm_q)

    async def ws_reader() -> None:
        try:
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if msg.get("bytes"):
                    b = msg["bytes"]
                    try:
                        in_q.put_nowait(b)
                    except asyncio.QueueFull:
                        pass
                elif msg.get("text"):
                    try:
                        data = json.loads(msg["text"])
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") == "stop":
                        break
        except WebSocketDisconnect:
            pass
        finally:
            try:
                in_q.put_nowait(None)
            except Exception:
                pass

    async def pcm_pump() -> None:
        try:
            while True:
                b = await pcm_q.get()
                if b is None:
                    break
                await websocket.send_bytes(b)
        except (WebSocketDisconnect, asyncio.CancelledError):
            raise
        except Exception:
            return

    async def text_pump() -> None:
        try:
            while True:
                t = await text_out.get()
                await websocket.send_json({"type": "agent_text", "text": t})
        except (WebSocketDisconnect, asyncio.CancelledError):
            raise
        except Exception:
            return

    t_reader = asyncio.create_task(ws_reader())
    t_pcm = asyncio.create_task(pcm_pump())
    t_txt = asyncio.create_task(text_pump())

    try:
        agent = BooklyLiveAgent(modality="AUDIO")
        await agent.run_voice_with_streams(
            _queue_mic_iter(in_q),
            speaker,
            text_out=text_out,
        )
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
        raise
    finally:
        for t in (t_reader, t_pcm, t_txt):
            t.cancel()
        try:
            pcm_q.put_nowait(None)
        except Exception:
            pass
        await asyncio.gather(t_reader, t_pcm, t_txt, return_exceptions=True)


def main() -> None:
    import uvicorn

    host = os.environ.get("BOOKLY_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("BOOKLY_WEB_PORT", "8765"))
    uvicorn.run("web_server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
