/**
 * Bookly browser voice client — PCM16 mono @ 16kHz to server,
 * playback @ 24kHz from server binary frames.
 */

const INPUT_RATE = 16000;
const OUTPUT_RATE = 24000;

const $ = (id) => document.getElementById(id);

function setStatus(mode) {
  const el = $("status");
  el.classList.remove("idle", "live");
  if (mode === "live") {
    el.textContent = "Live";
    el.classList.add("live");
  } else {
    el.textContent = "Idle";
    el.classList.add("idle");
  }
}

function appendLog(text, cls = "line") {
  const log = $("log");
  const div = document.createElement("div");
  div.className = cls;
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

function appendDebug(msg) {
  const log = $("debugLog");
  if (!log) {
    return;
  }
  const row = document.createElement("div");
  row.className = "debug-line";
  const kind = msg.kind;
  if (kind === "tool_call") {
    const blocked = msg.blocked ? " [blocked]" : "";
    row.textContent = `→ ${msg.name}${blocked} ${JSON.stringify(msg.args ?? {})}`;
  } else if (kind === "tool_response") {
    row.textContent = `← ${msg.name} ${JSON.stringify(msg.output)}`;
  } else {
    row.textContent = JSON.stringify(msg);
  }
  log.appendChild(row);
  log.scrollTop = log.scrollHeight;
}

function resampleFloat32(input, inputRate, outputRate) {
  if (inputRate === outputRate) {
    return input;
  }
  const ratio = inputRate / outputRate;
  const outLen = Math.max(1, Math.floor(input.length / ratio));
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const src = i * ratio;
    const i0 = Math.floor(src);
    const frac = src - i0;
    const s0 = input[i0] ?? 0;
    const s1 = input[i0 + 1] ?? s0;
    out[i] = s0 * (1 - frac) + s1 * frac;
  }
  return out;
}

function floatToInt16(f32) {
  const out = new Int16Array(f32.length);
  for (let i = 0; i < f32.length; i++) {
    const x = Math.max(-1, Math.min(1, f32[i]));
    out[i] = x < 0 ? x * 0x8000 : x * 0x7fff;
  }
  return out;
}

function wsUrl() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}/ws/voice`;
}

let ws = null;
let captureCtx = null;
let captureStream = null;
let processor = null;
let muteNode = null;
let playCtx = null;
let nextPlayTime = 0;

function ensurePlayContext() {
  if (playCtx) {
    return playCtx;
  }
  try {
    playCtx = new AudioContext({ sampleRate: OUTPUT_RATE });
  } catch {
    playCtx = new AudioContext();
  }
  nextPlayTime = playCtx.currentTime;
  return playCtx;
}

function playPcm16(buffer) {
  const ctx = ensurePlayContext();
  const int16 = new Int16Array(buffer);
  if (int16.length === 0) {
    return;
  }
  const buf = ctx.createBuffer(1, int16.length, OUTPUT_RATE);
  const ch = buf.getChannelData(0);
  for (let i = 0; i < int16.length; i++) {
    ch[i] = int16[i] / 32768;
  }
  const src = ctx.createBufferSource();
  src.buffer = buf;
  const startAt = Math.max(ctx.currentTime, nextPlayTime);
  src.connect(ctx.destination);
  src.start(startAt);
  nextPlayTime = startAt + buf.duration;
}

function stopCapture() {
  if (processor) {
    try {
      processor.disconnect();
    } catch {
      /* ignore */
    }
    processor.onaudioprocess = null;
    processor = null;
  }
  if (muteNode) {
    try {
      muteNode.disconnect();
    } catch {
      /* ignore */
    }
    muteNode = null;
  }
  if (captureStream) {
    captureStream.getTracks().forEach((t) => t.stop());
    captureStream = null;
  }
  if (captureCtx) {
    captureCtx.close().catch(() => {});
    captureCtx = null;
  }
}

function stopAll() {
  stopCapture();
  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify({ type: "stop" }));
    } catch {
      /* ignore */
    }
    ws.close();
  }
  ws = null;
  if (playCtx) {
    playCtx.close().catch(() => {});
    playCtx = null;
  }
  nextPlayTime = 0;
  setStatus("idle");
  $("btnStart").disabled = false;
  $("btnStop").disabled = true;
}

async function startVoice() {
  $("btnStart").disabled = true;
  $("btnStop").disabled = false;
  $("log").innerHTML = "";
  const dbg = $("debugLog");
  if (dbg) {
    dbg.innerHTML = "";
  }
  $("greeting").textContent = "Connecting…";
  $("greeting").classList.add("muted");

  ws = new WebSocket(wsUrl());
  ws.binaryType = "arraybuffer";

  ws.onmessage = (ev) => {
    if (ev.data instanceof ArrayBuffer) {
      playPcm16(ev.data);
      return;
    }
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === "greeting") {
        $("greeting").textContent = msg.text || "";
        $("greeting").classList.remove("muted");
        appendLog(msg.text, "line agent");
      } else if (msg.type === "agent_text") {
        appendLog(msg.text, "line agent");
      } else if (msg.type === "error") {
        appendLog(`Error: ${msg.message}`, "line system");
      } else if (msg.type === "debug") {
        appendDebug(msg);
      }
    } catch {
      /* ignore */
    }
  };

  ws.onclose = () => {
    stopCapture();
    setStatus("idle");
    $("btnStart").disabled = false;
    $("btnStop").disabled = true;
  };

  await new Promise((resolve, reject) => {
    ws.addEventListener("open", () => resolve(), { once: true });
    ws.addEventListener(
      "error",
      () => reject(new Error("WebSocket connection failed")),
      { once: true },
    );
  });

  const pctx = ensurePlayContext();
  if (pctx.state === "suspended") {
    await pctx.resume();
  }

  captureStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
    },
    video: false,
  });

  captureCtx = new AudioContext();
  if (captureCtx.state === "suspended") {
    await captureCtx.resume();
  }
  const source = captureCtx.createMediaStreamSource(captureStream);
  const bufferSize = 4096;
  processor = captureCtx.createScriptProcessor(bufferSize, 1, 1);
  muteNode = captureCtx.createGain();
  muteNode.gain.value = 0;

  processor.onaudioprocess = (e) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return;
    }
    const input = e.inputBuffer.getChannelData(0);
    const resampled = resampleFloat32(input, captureCtx.sampleRate, INPUT_RATE);
    const pcm = floatToInt16(resampled);
    ws.send(pcm.buffer);
  };

  source.connect(processor);
  processor.connect(muteNode);
  muteNode.connect(captureCtx.destination);

  setStatus("live");
}

$("btnStart").addEventListener("click", () => {
  startVoice().catch((err) => {
    appendLog(String(err), "line system");
    stopAll();
  });
});

$("btnStop").addEventListener("click", () => {
  stopAll();
});

window.addEventListener("beforeunload", () => stopAll());
