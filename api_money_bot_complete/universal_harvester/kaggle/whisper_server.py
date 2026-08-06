#!/usr/bin/env python3
"""
Whisper GPU Server for Kaggle (2× T4).  Paste this into a fresh Kaggle
notebook, run all cells, then expose with Cloudflare Tunnel:

    !wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
    !chmod +x cloudflared-linux-amd64
    !./cloudflared-linux-amd64 tunnel --url http://localhost:5000 &

Environment:
    WHISPER_MODEL=base          # tiny / base / small / medium / large-v3
    PORT=5000
    DEVICE="cuda"               # or "cpu" if T4 unavailable

Endpoints:
    POST /transcribe    {audio: <base64>, language: "en"}
    GET  /health        → {"status": "ok", "gpu": "T4", "model": "base"}
"""

import os
import io
import base64
import json
import tempfile
import warnings
from concurrent.futures import ThreadPoolExecutor

# Flask is pre-installed on Kaggle; reinstall if not
from flask import Flask, request, jsonify  # type: ignore

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")
PORT = int(os.getenv("PORT", "5000"))
GPU_COUNT = 2  # Kaggle gives us 2× T4s

# ─────────────────────────────────────────────────────────────────────────────
# Model setup – load once, cache in global
# ─────────────────────────────────────────────────────────────────────────────
_whisper_model = None


def load_model():
    """Idempotent load – returns whisper model on gpu if:disable gpu if unavailable."""
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model

    import torch
    import whisper as wisp

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[KaggleServer] Loading Whisper model='{MODEL_SIZE}' on device='{device}'")

    model = wisp.load_model(MODEL_SIZE).to(device)
    _whisper_model = model
    print("[KaggleServer] Model loaded – ready for inference")
    return model


# ─────────────────────────────────────────────────────────────────────────────
# Flask app
# ─────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=GPU_COUNT)


@app.route("/health", methods=["GET"])
def health():
    """Lightweight health probe."""
    import torch
    gpu = "T4" if torch.cuda.is_available() else "cpu"
    return jsonify({"status": "ok", "gpu": gpu, "model": MODEL_SIZE}), 200


# ---------------------------------------------------------------------------
# /transcribe – main endpoint
# ---------------------------------------------------------------------------

@app.route("/transcribe", methods=["POST"])
def transcribe():
    try:
        data = request.get_json(force=True)
        audio_b64 = data.get("audio", "")
        language = data.get("language", "en")
        temperature = data.get("temperature", 0.0)

        if not audio_b64:
            return jsonify({"error": "missing 'audio' field"}), 400

        # Decode base64 → temp file
        audio_bytes = base64.b64decode(audio_b64)
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(audio_bytes)

        # Run inference
        model = load_model()
        result = model.transcribe(
            tmp_path,
            language=language,
            initial_prompt="This audio contains spoken digits or letters.",
            temperature=temperature,
            condition_on_previous_text=False,
        )

        # Cleanup
        os.remove(tmp_path)

        return jsonify({
            "text": result["text"],
            "language": result.get("language"),
        }), 200

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    print(f"[KaggleServer] Starting Whisper server on port {PORT} …")
    # dummy warm-up to avoid cold-start on first request
    try:
        load_model()
    except Exception as e:
        warnings.warn(f"Model warm-up failed: {e}")
        # still start the server so the tunnel is alive even if model load fails
    app.run(host="0.0.0.0", port=PORT, threaded=True)
