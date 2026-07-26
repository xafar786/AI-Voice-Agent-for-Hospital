from __future__ import annotations

from functools import lru_cache
from typing import Any
import json
import re
from pydantic import BaseModel, Field

from config import (
    OPENAI_API_KEY,
    OPENAI_CLASSIFIER_MAX_OUTPUT_TOKENS,
    OPENAI_MODEL,
    OPENAI_REPLY_MAX_OUTPUT_TOKENS,
)
from domain.intents import INTENT_SCHEMA_DESCRIPTION
from domain.doctor_matching import doctor_name_key, doctor_name_match_score, doctor_names_match
from domain.id_normalization import (
    normalize_appointment_id,
    normalize_doctor_id,
    normalize_patient_id,
)
from domain.phone_normalization import normalize_phone_number
from domain.symptom_routing import infer_department_from_symptoms
from schemas import IntentName, IntentResult


VALID_INTENTS = {
    "book_appointment",
    "reschedule_appointment",
    "cancel_appointment",
    "check_availability",
    "list_doctors",
    "end_conversation",
    "greeting",
    "other",
}


class ExtractedEntities(BaseModel):
    patient_name: str | None = None
    patient_type: str | None = None
    patient_id: str | None = None
    phone: str | None = None
    doctor_id: str | None = None
    doctor_name: str | None = None
    department: str | None = None
    date: str | None = None
    natural_date: str | None = None
    time: str | None = None
    natural_time: str | None = None
    appointment_id: str | None = None
    reason: str | None = None
    confirmation: bool | None = None


class ClassifiedIntent(BaseModel):
    intent: IntentName
    confidence: float = Field(ge=0.0, le=1.0)
    entities: ExtractedEntities


VOICE_AGENT_SYSTEM_PROMPT = """
You are the hospital's Urdu-speaking appointment receptionist in a live phone call.

Your responsibilities:
1. Understand Urdu, Roman Urdu, and mixed English naturally using the conversation context.
2. Help with doctor discovery, availability, booking, rescheduling, and cancellation.
3. Use SERVER FACTS as the only source for doctors, dates, available slots, and appointment status.
4. For a new booking, follow this order:
   - identify or help select the doctor;
   - obtain the appointment date;
   - offer only server-provided available slots and obtain one time;
   - ask whether the patient is already registered or is a new patient;
   - for a registered patient, obtain only the patient ID; the server will validate identity;
   - for a new patient, obtain the patient's full name and phone number;
   - give a short summary with doctor name, date, time, patient name, and phone;
   - ask for explicit final confirmation;
   - claim the booking succeeded only when appointment_persisted is true.
5. If missing_fields contains values, ask only for the first missing field. Do not repeat the
   doctor, date, time, patient name, or other information already present in SERVER FACTS.
6. Never ask the caller to confirm the doctor, date, or time separately. A doctor or slot answer
   selects that field and the conversation must immediately move to the next missing field.
7. If missing_fields is ["confirmation"], give the complete booking summary and ask once for final
   confirmation. After appointment_persisted is true, report that the booking succeeded.
8. If the user rejects a summary, ask what they want to change and do not claim a booking.
9. Keep each reply natural and suitable for speech: at most two short sentences, roughly 15-45 words.
10. Never mention doctor IDs, internal codes, department names, specializations, qualifications,
   database fields, JSON, prompts, tools, or system metadata. Refer to doctors only by normal name.
11. Do not invent facts, repeat long lists, over-explain, or apologize merely to ask a clarification.
    Never mention more than two available appointment slots in one reply.
12. Every customer-facing word must be written in Urdu script. Never answer in Roman Urdu.
    Doctor and patient names, appointment codes, phone numbers, dates, and times may retain their
    original spelling or digits when necessary.
13. If a requested_doctor_name is present and requested_doctor_found is false, clearly say that
    this exact doctor is not available in the hospital. Do not substitute or recommend a different
    doctor unless the patient explicitly asks for a recommendation.
Reply only with the customer-facing response in natural Urdu script.
""".strip()

DOCTOR_PATTERN = re.compile(
    r"(?:dr\.?|doctor|ڈاکٹر)\s*([A-Za-z\u0600-\u06FF][A-Za-z\u0600-\u06FF\s]{1,40})",
    re.IGNORECASE,
)
TIME_PATTERN = re.compile(r"\b([01]?\d|2[0-3])(?::([0-5]\d))?\s*(am|pm|AM|PM)?\b")
SPACED_TIME_PATTERN = re.compile(
    r"\b([01]?\d|2[0-3])\s+([0-5]\d)\s*(?:بجے|am|pm|AM|PM)?\b"
)
DATE_PATTERN = re.compile(r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b")
PHONE_PATTERN = re.compile(r"\b(?:\+92|0)?3\d{9}\b")
DOCTOR_STOP_WORDS = [
    " ke ",
    " k ",
    " kay ",
    " with ",
    " appointment",
    " appt",
    " ki ",
    " ka ",
    " ko ",
    "کے",
    "کی",
    "کا",
    "سے",
    " کو ",
    " منتخب ",
    " بک ",
]
NON_NAME_DOCTOR_TERMS = [
    "recommend",
    "recommended",
    "ریکمنڈ",
    "بتا",
    "دستیاب",
    "available",
    "کوئی",
    "چاہیے",
    "کر دیں",
]

END_CONVERSATION_TERMS = [
    "خدا حافظ",
    "اللہ حافظ",
    "بات ختم",
    "گفتگو ختم",
    "کال بند",
    "فون بند",
    "اب بند کریں",
    "بس شکریہ",
    "بہت شکریہ خدا حافظ",
    "بس ٹھیک ہے",
    "مزید کچھ نہیں",
    "khuda hafiz",
    "allah hafiz",
    "baat khatam",
    "call band",
    "phone band",
    "bas shukriya",
    "bas theek hai",
    "goodbye",
    "good bye",
    "bye bye",
    "end call",
    "end the call",
    "end conversation",
    "close conversation",
    "stop conversation",
    "hang up",
    "that's all goodbye",
    "no thanks goodbye",
]

URDU_SCRIPT_PATTERN = re.compile(r"[\u0600-\u06FF]")
DATE_REFERENCE_TERMS = [
    "آج",
    "کل",
    "پرسوں",
    "aaj",
    "kal",
    "parson",
    "today",
    "tomorrow",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "جنوری",
    "فروری",
    "مارچ",
    "اپریل",
    "مئی",
    "جون",
    "جولائی",
    "اگست",
    "ستمبر",
    "اکتوبر",
    "نومبر",
    "دسمبر",
]

SYMPTOM_ONSET_PATTERNS = [
    re.compile(
        r"\b(?:since|from)\s+(?:last\s+night|yesterday|this\s+morning|"
        r"this\s+afternoon|this\s+evening)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:kal\s+raat|aaj\s+subah|aaj\s+shaam|kal|aaj)\s+se\b",
        re.IGNORECASE,
    ),
    re.compile(r"(?:کل رات|آج صبح|آج دوپہر|آج شام|کل|آج)\s+سے"),
    re.compile(r"\b(?:fell|hurt|injured)\s+yesterday\b", re.IGNORECASE),
    re.compile(r"\bkal\s+(?:gira|giri|chot)\b", re.IGNORECASE),
    re.compile(r"کل\s+(?:گرا|گری|چوٹ)"),
]


def _has_symptom_onset_date(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in SYMPTOM_ONSET_PATTERNS)


def get_llm_status() -> dict[str, str]:
    if not OPENAI_API_KEY:
        return {"status": "Down", "detail": "OPENAI_API_KEY is not configured."}

    try:
        from openai import OpenAI  # noqa: F401
    except ImportError as exc:
        return {"status": "Down", "detail": f"Missing dependency: {exc.name}"}

    if _get_openai_client.cache_info().currsize:
        return {"status": "Active", "detail": f"OpenAI LLM client is ready ({OPENAI_MODEL})."}
    return {"status": "Ready", "detail": f"OpenAI LLM is configured ({OPENAI_MODEL})."}


@lru_cache(maxsize=1)
def _get_openai_client():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "OpenAI dependency is not installed. Run `pip install -r requirements.txt`."
        ) from exc

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    return OpenAI(api_key=OPENAI_API_KEY)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _normalize_time(match: re.Match[str]) -> str:
    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    meridiem = (match.group(3) or "").lower()
    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute:02d}"


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(
        re.search(
            rf"(?<!\w){re.escape(phrase)}(?!\w)",
            text,
            flags=re.IGNORECASE,
        )
    )


def _clean_doctor_name(value: str) -> str:
    cleaned = f" {value.strip(' .،,')} "
    lowered = cleaned.lower()
    cut_at = len(cleaned)
    for stop_word in DOCTOR_STOP_WORDS:
        idx = lowered.find(stop_word)
        if idx >= 0:
            cut_at = min(cut_at, idx)
    return cleaned[:cut_at].strip(" .،,")


def _heuristic_entities(text: str) -> dict[str, Any]:
    entities: dict[str, Any] = {}

    if match := DOCTOR_PATTERN.search(text):
        name = _clean_doctor_name(match.group(1))
        lowered_name = name.lower()
        if name and not any(term.lower() in lowered_name for term in NON_NAME_DOCTOR_TERMS):
            entities["doctor_name"] = f"Dr. {name}"
    if match := DATE_PATTERN.search(text):
        entities["date"] = match.group(1).replace("/", "-")
    elif _contains_phrase(text, "آج") or _contains_phrase(text, "aaj"):
        entities["natural_date"] = "aaj"
    elif _contains_phrase(text, "کل") or _contains_phrase(text, "kal"):
        entities["natural_date"] = "kal"
    elif _contains_phrase(text, "پرسوں") or _contains_phrase(text, "parson"):
        entities["natural_date"] = "parson"

    if match := SPACED_TIME_PATTERN.search(text):
        entities["time"] = f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"
    elif match := TIME_PATTERN.search(text):
        entities["time"] = _normalize_time(match)
    elif "صبح" in text:
        entities["natural_time"] = "subah"
    elif "دوپہر" in text:
        entities["natural_time"] = "dopehar"
    elif "شام" in text:
        entities["natural_time"] = "shaam"

    if match := PHONE_PATTERN.search(text):
        entities["phone"] = match.group(0)
    if patient_id := normalize_patient_id(text):
        entities["patient_id"] = patient_id
    if appointment_id := normalize_appointment_id(text):
        entities["appointment_id"] = appointment_id
    if doctor_id := normalize_doctor_id(text):
        entities["doctor_id"] = doctor_id

    lowered = text.lower()
    if (
        any(
            term in lowered
            for term in [
                "registered", "registered user", "existing patient",
                "old patient", "purana patient", "pehle se registered",
            ]
        )
        or any(term in text for term in ["رجسٹرڈ", "پرانا مریض", "پہلے سے مریض"])
    ):
        entities["patient_type"] = "registered"
    elif (
        any(
            term in lowered
            for term in ["new patient", "naya patient", "new user", "naya user"]
        )
        or any(term in text for term in ["نیا مریض", "نئے مریض", "نیا یوزر", "پہلی بار"])
    ):
        entities["patient_type"] = "new"
    if symptom_department := infer_department_from_symptoms(text):
        entities["department"] = symptom_department
        entities["reason"] = text
        entities["_department_explicit"] = True
        if _has_symptom_onset_date(text) and not DATE_PATTERN.search(text):
            # "Since last night/yesterday" describes symptom duration, not the
            # requested appointment date.
            entities.pop("date", None)
            entities.pop("natural_date", None)
    return entities


def _heuristic_intent(transcript: str) -> IntentResult:
    text = (transcript or "").strip()
    lowered = text.lower()
    entities = _heuristic_entities(text)

    if any(word in lowered for word in ["doctor list", "list doctors", "available doctors"]) or any(
        word in text for word in ["ڈاکٹرز", "ڈاکٹروں", "فہرست"]
    ):
        return IntentResult(intent="list_doctors", confidence=0.8, entities=entities)
    if any(word in lowered for word in ["cancel", "delete appointment"]) or "کینسل" in text or "منسوخ" in text:
        return IntentResult(intent="cancel_appointment", confidence=0.78, entities=entities)
    if any(word in lowered for word in ["reschedule", "change appointment"]) or "تبدیل" in text:
        return IntentResult(intent="reschedule_appointment", confidence=0.78, entities=entities)
    if any(word in lowered for word in ["availability", "available slot", "available time"]) or any(
        word in text for word in ["دستیاب", "وقت مل"]
    ):
        return IntentResult(intent="check_availability", confidence=0.74, entities=entities)
    if any(word in lowered for word in ["book", "appointment"]) or any(
        word in text for word in ["اپائنٹمنٹ", "ملاقات", "بک"]
    ):
        return IntentResult(intent="book_appointment", confidence=0.72, entities=entities)
    if entities.get("department"):
        return IntentResult(intent="check_availability", confidence=0.82, entities=entities)
    if any(word in lowered for word in ["hello", "hi", "salam", "assalam", "hey"]) or any(
        word in text for word in ["سلام", "السلام"]
    ):
        return IntentResult(intent="greeting", confidence=0.85, entities=entities)
    return IntentResult(intent="other", confidence=0.6, entities=entities)


def _is_end_conversation(transcript: str) -> bool:
    text = re.sub(r"\s+", " ", (transcript or "").strip().lower())
    return any(term.lower() in text for term in END_CONVERSATION_TERMS)


def _mentions_date(transcript: str) -> bool:
    text = (transcript or "").strip()
    return bool(
        DATE_PATTERN.search(text)
        or any(_contains_phrase(text, term) for term in DATE_REFERENCE_TERMS)
    )


def _is_urdu_script_reply(text: str) -> bool:
    letters = [char for char in (text or "") if char.isalpha()]
    if not letters:
        return False
    urdu_letters = [
        char for char in letters
        if URDU_SCRIPT_PATTERN.fullmatch(char)
    ]
    return len(urdu_letters) >= 4 and len(urdu_letters) / len(letters) >= 0.6


def _rewrite_reply_in_urdu(reply: str) -> str:
    response = _get_openai_client().responses.create(
        model=OPENAI_MODEL,
        input=[
            {
                "role": "developer",
                "content": (
                    "Convert the supplied hospital receptionist reply completely into natural Urdu "
                    "script. Do not use Roman Urdu. Preserve every fact exactly. Keep doctor and "
                    "patient names, appointment codes, phone numbers, dates, and times unchanged "
                    "when necessary. Do not add or remove information. Return only the Urdu reply."
                ),
            },
            {"role": "user", "content": reply},
        ],
        reasoning={"effort": "minimal"},
        max_output_tokens=OPENAI_REPLY_MAX_OUTPUT_TOKENS,
        text={"verbosity": "low"},
    )
    rewritten = (response.output_text or "").strip()
    if _is_urdu_script_reply(rewritten):
        return rewritten
    return "براہ کرم اپنی درخواست دوبارہ بتائیے تاکہ میں درست رہنمائی کر سکوں۔"


def _booking_follow_up(
    transcript: str,
    *,
    expected_fields: list[str] | None,
    previous_intent: str | None,
    active_intent: str | None,
) -> IntentResult | None:
    text = (transcript or "").strip()
    lowered = text.lower()
    expected = (expected_fields or [None])[0]
    workflow_intent = active_intent or previous_intent

    yes_terms = ["yes", "yeah", "confirm", "confirmed", "han", "haan", "جی", "ہاں", "کنفرم", "ٹھیک ہے"]
    no_terms = ["no", "نہیں", "نهيں", "cancel", "کینسل"]

    current_entities = _heuristic_entities(text)
    if expected == "patient_type":
        patient_type = current_entities.get("patient_type")
        if patient_type:
            entities = {"patient_type": patient_type}
            if current_entities.get("patient_id"):
                entities["patient_id"] = current_entities["patient_id"]
            return IntentResult(
                intent="book_appointment",
                confidence=1.0,
                entities=entities,
            )

    if expected in {"patient_id", "valid_patient_id"}:
        patient_id = current_entities.get("patient_id") or normalize_patient_id(
            text,
            allow_digits_only=True,
        )
        if patient_id:
            return IntentResult(
                intent="book_appointment",
                confidence=1.0,
                entities={"patient_id": patient_id},
            )

    if expected in {"appointment_id", "valid_appointment"}:
        appointment_id = current_entities.get("appointment_id") or normalize_appointment_id(
            text,
            allow_digits_only=True,
        )
        return IntentResult(
            intent=workflow_intent if workflow_intent in {
                "cancel_appointment",
                "reschedule_appointment",
            } else "cancel_appointment",
            confidence=1.0,
            entities={"appointment_id": appointment_id} if appointment_id else {},
        )

    is_short_time_answer = bool(
        current_entities.get("time")
        and not current_entities.get("date")
        and not current_entities.get("natural_date")
        and not current_entities.get("phone")
        and not current_entities.get("doctor_name")
        and len(text.split()) <= 5
    )
    is_short_confirmation = bool(
        len(text.split()) <= 5
        and not current_entities.get("doctor_name")
        and not current_entities.get("department")
        and not current_entities.get("date")
        and not current_entities.get("natural_date")
        and not current_entities.get("time")
    )

    if expected == "confirmation":
        if is_short_confirmation and any(term in lowered or term in text for term in yes_terms):
            return IntentResult(intent="book_appointment", confidence=1.0, entities={"confirmation": True})
        if is_short_confirmation and any(term in lowered or term in text for term in no_terms):
            return IntentResult(intent="book_appointment", confidence=1.0, entities={"confirmation": False})

    if expected == "phone":
        phone = normalize_phone_number(text)
        # Keep this turn deterministic even when ASR captured too few digits.
        # It must never go back through the LLM and become a patient name.
        return IntentResult(
            intent="book_appointment",
            confidence=1.0,
            entities={"phone": phone} if phone else {},
        )

    # Short answers to slot questions must not be sent back through the LLM.
    # Otherwise the model can re-extract an older doctor/date from the history
    # and overwrite the authoritative thread state.
    if expected == "time":
        if is_short_time_answer and workflow_intent in {
            "book_appointment",
            "reschedule_appointment",
            "check_availability",
        }:
            return IntentResult(
                intent=workflow_intent,
                confidence=1.0,
                entities={"time": current_entities["time"]},
            )

    # Availability has no required "time" field, but callers commonly select
    # one of the offered slots in the very next turn.
    if is_short_time_answer and previous_intent == "check_availability":
        return IntentResult(
            intent="check_availability",
            confidence=1.0,
            entities={"time": current_entities["time"]},
        )

    if expected == "date":
        date_entities = {
            key: current_entities[key]
            for key in ("date", "natural_date")
            if current_entities.get(key)
        }
        if date_entities and workflow_intent in {
            "book_appointment",
            "reschedule_appointment",
            "check_availability",
        }:
            return IntentResult(intent=workflow_intent, confidence=1.0, entities=date_entities)

    if expected == "patient_name" and text and not current_entities.get("doctor_name"):
        cleaned = re.sub(
            r"^(?:my name is|name is|mera naam|میرا نام|نام)\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s*(?:ہے|hai)\s*$", "", cleaned, flags=re.IGNORECASE).strip(" .،")
        if cleaned:
            return IntentResult(intent="book_appointment", confidence=1.0, entities={"patient_name": cleaned})

    if previous_intent == "check_availability" and is_short_confirmation and any(
        term in lowered or term in text for term in yes_terms
    ):
        return IntentResult(intent="book_appointment", confidence=1.0, entities={"confirmation": True})
    return None


def _ground_doctor_entities(
    *,
    transcript: str,
    entities: dict[str, Any],
    heuristic_entities: dict[str, Any],
    doctors: list[dict[str, Any]],
) -> dict[str, Any]:
    grounded = dict(entities)
    raw_doctor_name = heuristic_entities.get("doctor_name")
    if not raw_doctor_name:
        transcript_key = doctor_name_key(transcript)
        explicit_candidates: list[tuple[int, dict[str, Any]]] = []
        patient_name_answer = any(
            marker in transcript.lower()
            for marker in ("میرا نام", "نام ہے", "my name", "name is", "mera naam")
        )
        if not patient_name_answer and (
            any(marker in transcript.lower() for marker in ("ڈاکٹر", "doctor", "dr."))
            or any(marker in transcript.lower() for marker in ("اپائنٹمنٹ", "appointment", "دستیاب", "available"))
        ):
            for doctor in doctors:
                alias_keys = [
                    doctor_name_key(alias)
                    for alias in (doctor.get("name"), doctor.get("urdu_name"))
                    if alias
                ]
                matching_keys = [
                    alias_key
                    for alias_key in alias_keys
                    if alias_key and alias_key in transcript_key
                ]
                if matching_keys:
                    explicit_candidates.append((max(map(len, matching_keys)), doctor))
        if explicit_candidates:
            longest = max(length for length, _ in explicit_candidates)
            longest_matches = [
                doctor for length, doctor in explicit_candidates if length == longest
            ]
            raw_doctor_name = longest_matches[0].get("name")
    if raw_doctor_name:
        scored_matches: list[tuple[float, dict[str, Any]]] = []
        for doctor in doctors:
            score = max(
                (
                    doctor_name_match_score(raw_doctor_name, alias)
                    for alias in (doctor.get("name"), doctor.get("urdu_name"))
                    if alias
                ),
                default=0.0,
            )
            if score >= 0.78:
                scored_matches.append((score, doctor))

        grounded.pop("doctor_id", None)
        if scored_matches:
            best_score = max(score for score, _ in scored_matches)
            best_matches = [
                doctor
                for score, doctor in scored_matches
                if abs(score - best_score) < 1e-9
            ]
            if len(best_matches) == 1:
                best_doctor = best_matches[0]
                grounded["doctor_id"] = best_doctor.get("doctor_id")
                grounded["doctor_name"] = best_doctor.get("name")
                grounded["department"] = best_doctor.get("department")
                grounded["_doctor_locked"] = True
            else:
                best_public_names = {
                    doctor_name_key(doctor.get("name"))
                    for doctor in best_matches
                    if doctor.get("name")
                }
                if len(best_public_names) == 1:
                    grounded["doctor_name"] = best_matches[0].get("name")
                    grounded["_doctor_locked"] = True
                else:
                    # Equal-quality matches for different doctors are a real
                    # ambiguity. Preserve what the caller said instead of
                    # selecting whichever database ID happens to sort first.
                    grounded["doctor_name"] = raw_doctor_name
                    grounded.pop("department", None)
                    grounded["_doctor_locked"] = False
            if not any(
                marker in transcript.lower()
                for marker in ("میرا نام", "نام ہے", "my name", "name is", "mera naam")
            ):
                grounded.pop("patient_name", None)
                grounded.pop("patient_type", None)
        else:
            grounded["doctor_name"] = raw_doctor_name
            grounded["_doctor_locked"] = False
        return grounded

    if not (grounded.get("doctor_id") or grounded.get("doctor_name")):
        return grounded

    mapped_doctor = None
    mapped_id = str(grounded.get("doctor_id") or "").upper()
    mapped_name = str(grounded.get("doctor_name") or "")
    for doctor in doctors:
        if mapped_id and str(doctor.get("doctor_id") or "").upper() == mapped_id:
            mapped_doctor = doctor
            break
        if mapped_name and doctor_names_match(mapped_name, doctor.get("name")):
            mapped_doctor = doctor
            break
    mapped_key = doctor_name_key((mapped_doctor or {}).get("name"))
    if mapped_doctor and mapped_key and mapped_key in doctor_name_key(transcript):
        grounded["doctor_id"] = mapped_doctor.get("doctor_id")
        grounded["doctor_name"] = mapped_doctor.get("name")
        grounded["_doctor_locked"] = True
    else:
        grounded.pop("doctor_id", None)
        grounded.pop("doctor_name", None)
    return grounded


def _detect_with_openai(
    transcript: str,
    *,
    conversation_history: list[dict[str, Any]] | None = None,
    active_intent: str | None = None,
    doctors: list[dict[str, Any]] | None = None,
) -> IntentResult:
    client = _get_openai_client()
    recent_history = (conversation_history or [])[-8:]
    history_text = "\n".join(
        f"{str(item.get('role') or 'unknown')}: {str(item.get('content') or '')}"
        for item in recent_history
    )
    doctor_catalog = [
        {
            "doctor_id": doctor.get("doctor_id"),
            "name": doctor.get("name"),
            "urdu_name": doctor.get("urdu_name"),
            "department": doctor.get("department"),
        }
        for doctor in (doctors or [])
    ]
    prompt = (
        f"{INTENT_SCHEMA_DESCRIPTION}\n\n"
        f"Conversation so far:\n{history_text or '(new conversation)'}\n\n"
        f"Current active intent: {active_intent or 'none'}\n"
        f"Actual doctor catalog: {json.dumps(doctor_catalog, ensure_ascii=False)}\n"
        f"Latest patient message:\n{transcript}\n\n"
        "Classify the latest message in the context of the conversation. If it is a short "
        "answer to a clarification question, keep the active intent. Extract supported fields "
        "from the latest message. Resolve Urdu pronunciations/transliterations of doctor names "
        "to the exact catalog name and doctor_id when the match is clear. A request to book or "
        "make an appointment is book_appointment; a request only asking which times are free is "
        "check_availability. Put today/tomorrow/aaj/kal/parson in natural_date, not date. "
        "Examples: 'ڈاکٹر فہد کل کس وقت دستیاب ہیں؟' => check_availability with doctor_name "
        "Dr. Fahad and natural_date kal. 'Doctor Fahad kal kis time available hain?' => "
        "check_availability. 'میں ڈاکٹر فہد سے اپائنٹمنٹ بک کرنا چاہتا ہوں' => book_appointment. "
        "After availability or a slot is offered, a spoken time selects that slot; it is not final "
        "confirmation. Never set confirmation=true unless the assistant's immediately preceding "
        "question was the final confirmation after the complete booking summary. Extract patient "
        "name and phone from short "
        "follow-up answers when the active intent is book_appointment. When active intent is "
        "book_appointment and the assistant asked for a name: 'میرا نام علی خان ہے' => "
        "book_appointment with patient_name Ali Khan. When it asked for phone: 'میرا نمبر "
        "03001234567 ہے' => book_appointment with phone 03001234567. "
        "Extract phone digits from Urdu, Roman Urdu, and English spoken digit words in sequence. "
        "When asked for final confirmation: 'جی ہاں، کنفرم کریں' => book_appointment with "
        "confirmation=true. "
        "When asked whether the patient is registered or new: 'میں رجسٹرڈ مریض ہوں' => "
        "book_appointment with patient_type registered; 'میں نیا مریض ہوں' => book_appointment "
        "with patient_type new. Extract patient IDs such as PC7 into patient_id. "
        "copy old doctor/date/time fields from history into entities; extract the latest answer only. "
        "Never substitute a different catalog doctor for a requested name. "
        "Return JSON only."
    )
    parsed: ClassifiedIntent | None = None
    last_error: Exception | None = None
    for effort in ("minimal", "low"):
        try:
            response = client.responses.parse(
                model=OPENAI_MODEL,
                input=prompt,
                reasoning={"effort": effort},
                max_output_tokens=OPENAI_CLASSIFIER_MAX_OUTPUT_TOKENS,
                text_format=ClassifiedIntent,
            )
            parsed = response.output_parsed
            if parsed:
                break
        except Exception as exc:
            last_error = exc

    if not parsed:
        if last_error:
            raise RuntimeError("OpenAI intent classification failed after retry.") from last_error
        raise RuntimeError("OpenAI intent classification returned no structured result.")

    intent = parsed.intent
    entities = parsed.entities.model_dump(exclude_none=True)
    heuristic_entities = _heuristic_entities(transcript)
    for key, value in heuristic_entities.items():
        entities.setdefault(key, value)
    if heuristic_entities.get("appointment_id"):
        entities["appointment_id"] = heuristic_entities["appointment_id"]
    if heuristic_entities.get("patient_id"):
        entities["patient_id"] = heuristic_entities["patient_id"]
    if heuristic_entities.get("date") or heuristic_entities.get("natural_date"):
        # Explicit date words in the latest utterance are authoritative. The
        # classifier must not turn "کل" into today or retain a stale date.
        entities.pop("date", None)
        entities.pop("natural_date", None)
        if heuristic_entities.get("date"):
            entities["date"] = heuristic_entities["date"]
        if heuristic_entities.get("natural_date"):
            entities["natural_date"] = heuristic_entities["natural_date"]
    if heuristic_entities.get("department"):
        entities["_department_explicit"] = True

    # A doctor becomes selectable only when the latest patient wording
    # phonetically matches the complete catalog name. This prevents the LLM
    # from replacing "Dr. Fahad" with an unrelated catalog entry.
    entities = _ground_doctor_entities(
        transcript=transcript,
        entities=entities,
        heuristic_entities=heuristic_entities,
        doctors=doctors or [],
    )
    # The model sometimes copies "today" from earlier context even when the
    # latest utterance only contains a doctor's name. Date memory is managed
    # by the session layer, so unmentioned date fields must be rejected here.
    if not _mentions_date(transcript):
        entities.pop("date", None)
        entities.pop("natural_date", None)
    confidence = parsed.confidence
    return IntentResult(
        intent=intent,
        confidence=confidence,
        entities={
            key: value
            for key, value in entities.items()
            if value not in [None, ""]
            and not (
                isinstance(value, str)
                and value.strip().lower() in {"null", "none", "n/a", "unknown"}
            )
        },
    )


def detect_intent(
    transcript: str,
    *,
    conversation_history: list[dict[str, Any]] | None = None,
    active_intent: str | None = None,
    doctors: list[dict[str, Any]] | None = None,
    expected_fields: list[str] | None = None,
    previous_intent: str | None = None,
) -> IntentResult:
    if not (transcript or "").strip():
        return IntentResult(intent="other", confidence=0.0, entities={})

    # Ending a call is deterministic and must take precedence over an active
    # booking field (for example, "بس ٹھیک ہے" must not become a patient name).
    if _is_end_conversation(transcript):
        return IntentResult(intent="end_conversation", confidence=1.0, entities={})

    heuristic = _heuristic_intent(transcript)

    booking_follow_up = _booking_follow_up(
        transcript,
        expected_fields=expected_fields,
        previous_intent=previous_intent,
        active_intent=active_intent,
    )
    if booking_follow_up:
        return booking_follow_up

    # Symptom routing is grounded in the departments present in the hospital
    # catalog and should not drift to an unrelated intent or invented doctor.
    if heuristic.intent == "check_availability" and heuristic.entities.get("reason"):
        return heuristic

    # Greeting is the only fully local conversational response. Transactional
    # messages go through the LLM so Urdu phrasing and intent changes are not
    # forced into a keyword-based branch.
    if heuristic.intent == "greeting":
        return heuristic
    classified = _detect_with_openai(
        transcript,
        conversation_history=conversation_history,
        active_intent=active_intent,
        doctors=doctors,
    )
    if (
        heuristic.intent == "book_appointment"
        and classified.intent in {"check_availability", "other"}
    ):
        # An explicit "book appointment" instruction must not drift back to a
        # read-only availability turn merely because availability came first.
        classified.intent = "book_appointment"
    elif (
        heuristic.intent == "check_availability"
        and classified.intent in {"other", "list_doctors", "greeting"}
    ):
        classified.intent = "check_availability"
    if (
        classified.entities.get("appointment_id")
        and classified.intent == "book_appointment"
        and (
            classified.entities.get("date")
            or classified.entities.get("natural_date")
            or classified.entities.get("time")
        )
    ):
        # An existing appointment ID plus a replacement date/time describes
        # rescheduling, even when colloquial Urdu omits "ری شیڈول".
        classified.intent = "reschedule_appointment"
    return classified


def generate_grounded_reply(
    *,
    transcript: str,
    intent: IntentResult,
    conversation_history: list[dict[str, Any]],
    facts: dict[str, Any],
) -> str:
    """Generate natural Urdu while treating backend-calculated facts as authoritative."""
    recent_history = conversation_history[-8:]
    public_entities = {
        key: value
        for key, value in intent.entities.items()
        if key not in {"doctor_id", "department"} and not key.startswith("_")
    }
    prompt = (
        f"CONVERSATION: {json.dumps(recent_history, ensure_ascii=False, default=str)}\n"
        f"LATEST USER MESSAGE: {transcript}\n"
        f"PARSED INTENT: {json.dumps({'intent': intent.intent, 'entities': public_entities}, ensure_ascii=False)}\n"
        f"SERVER FACTS: {json.dumps(facts, ensure_ascii=False, default=str)}\n\n"
        "Return only the Urdu reply text."
    )
    response = _get_openai_client().responses.create(
        model=OPENAI_MODEL,
        input=[
            {"role": "developer", "content": VOICE_AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        reasoning={"effort": "low"},
        max_output_tokens=OPENAI_REPLY_MAX_OUTPUT_TOKENS,
        text={"verbosity": "low"},
    )
    reply = (response.output_text or "").strip()
    if not reply:
        raise RuntimeError("OpenAI LLM did not return an assistant reply.")
    return reply if _is_urdu_script_reply(reply) else _rewrite_reply_in_urdu(reply)
