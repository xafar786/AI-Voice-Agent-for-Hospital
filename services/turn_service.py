from typing import Any

from schemas import TurnResponse
from services.dialogue_service import generate_agent_text
from services.llm_service import detect_intent
from services.tts_service import synthesize_tts_base64
from storage.mongo_store import MongoStore


def process_turn(*, session_id: str, transcript: str, return_tts: bool, store: MongoStore) -> TurnResponse:
    intent = detect_intent(transcript)
    assistant_text = generate_agent_text(intent, transcript)

    tts_b64 = None
    mime = None
    if return_tts:
        tts_b64, mime = synthesize_tts_base64(assistant_text)

    store.append_session(session_id, "user", transcript)
    store.append_session(session_id, "assistant", assistant_text)
    store.persist_turn(
        session_id=session_id,
        transcript=transcript,
        intent_name=intent.intent,
        confidence=float(intent.confidence),
        entities=dict(intent.entities),
        assistant_text=assistant_text,
        audio_mime=mime or "audio/mpeg",
    )

    return TurnResponse(
        transcript=transcript,
        intent=intent,
        assistant_text=assistant_text,
        tts_audio_base64=tts_b64,
        audio_mime=mime or "audio/mpeg",
    )


def to_call_log_view(log: dict[str, Any]) -> dict[str, Any]:
    entities = dict(log.get("entities") or {})
    return {
        "id": log.get("id"),
        "session_id": log.get("session_id"),
        "patient_name": entities.get("patient_name") or "Unknown Caller",
        "phone": entities.get("phone"),
        "intent": log.get("intent"),
        "confidence": log.get("confidence"),
        "transcript": log.get("transcript"),
        "assistant_text": log.get("assistant_text"),
        "status": log.get("status", "Completed"),
        "created_at": log.get("created_at"),
    }
