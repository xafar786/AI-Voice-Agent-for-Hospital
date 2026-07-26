import base64

import requests

from config import (
    OPENAI_API_KEY,
    OPENAI_TTS_INSTRUCTIONS,
    OPENAI_TTS_CONNECT_TIMEOUT_SECONDS,
    OPENAI_TTS_MODEL,
    OPENAI_TTS_RESPONSE_FORMAT,
    OPENAI_TTS_READ_TIMEOUT_SECONDS,
    OPENAI_TTS_VOICE,
)


OPENAI_SPEECH_URL = "https://api.openai.com/v1/audio/speech"
MIME_BY_RESPONSE_FORMAT = {
    "mp3": "audio/mpeg",
    "opus": "audio/ogg",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "pcm": "audio/pcm",
}


def _mime_for_response_format(response_format: str) -> str:
    return MIME_BY_RESPONSE_FORMAT.get((response_format or "mp3").lower(), "audio/mpeg")


def get_tts_mime_type() -> str:
    return _mime_for_response_format(OPENAI_TTS_RESPONSE_FORMAT)


def get_tts_status() -> dict[str, str]:
    if not OPENAI_API_KEY:
        return {"status": "Down", "detail": "OPENAI_API_KEY is not configured."}
    if not OPENAI_TTS_MODEL:
        return {"status": "Down", "detail": "OPENAI_TTS_MODEL is not configured."}
    if not OPENAI_TTS_VOICE:
        return {"status": "Down", "detail": "OPENAI_TTS_VOICE is not configured."}
    return {
        "status": "Ready",
        "detail": f"OpenAI TTS is configured ({OPENAI_TTS_MODEL}, voice: {OPENAI_TTS_VOICE}).",
    }


def synthesize_tts_base64(text: str) -> tuple[str, str]:
    cleaned_text = (text or "").strip()
    if not cleaned_text:
        return "", get_tts_mime_type()
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    payload = {
        "model": OPENAI_TTS_MODEL,
        "voice": OPENAI_TTS_VOICE,
        "input": cleaned_text,
        "response_format": OPENAI_TTS_RESPONSE_FORMAT,
        "instructions": OPENAI_TTS_INSTRUCTIONS,
    }
    response = requests.post(
        OPENAI_SPEECH_URL,
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=(OPENAI_TTS_CONNECT_TIMEOUT_SECONDS, OPENAI_TTS_READ_TIMEOUT_SECONDS),
    )
    response.raise_for_status()
    if not response.content:
        raise RuntimeError("OpenAI TTS returned an empty audio response.")
    return (
        base64.b64encode(response.content).decode("utf-8"),
        get_tts_mime_type(),
    )
