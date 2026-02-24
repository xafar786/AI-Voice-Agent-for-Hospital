from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, Any

IntentName = Literal[
    "book_appointment",
    "reschedule_appointment",
    "cancel_appointment",
    "check_availability",
    "list_doctors",
    "greeting",
    "other"
]

class IntentResult(BaseModel):
    intent: IntentName
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)
    entities: Dict[str, Any] = Field(default_factory=dict)

class TurnResponse(BaseModel):
    transcript: str
    intent: IntentResult
    assistant_text: str
    tts_audio_base64: Optional[str] = None
    audio_mime: Optional[str] = "audio/mpeg"