from schemas import IntentResult


def detect_intent(transcript: str) -> IntentResult:
    text = (transcript or "").strip().lower()

    if any(word in text for word in ["hello", "hi", "salam", "assalam", "hey"]):
        return IntentResult(intent="greeting", confidence=0.85, entities={})

    if any(word in text for word in ["doctor list", "list doctors", "available doctors"]):
        return IntentResult(intent="list_doctors", confidence=0.8, entities={})

    if any(word in text for word in ["availability", "available slot", "available time"]):
        return IntentResult(intent="check_availability", confidence=0.75, entities={})

    if any(word in text for word in ["book", "appointment"]):
        return IntentResult(intent="book_appointment", confidence=0.7, entities={})

    if any(word in text for word in ["reschedule", "change appointment"]):
        return IntentResult(intent="reschedule_appointment", confidence=0.75, entities={})

    if any(word in text for word in ["cancel", "delete appointment"]):
        return IntentResult(intent="cancel_appointment", confidence=0.75, entities={})

    return IntentResult(intent="other", confidence=0.6, entities={})
