from typing import Any
from concurrent.futures import ThreadPoolExecutor
import re

from schemas import TurnResponse
from services.dialogue_service import build_receptionist_context, generate_agent_text, get_missing_fields
from services.llm_service import detect_intent, generate_grounded_reply
from services.tts_service import get_tts_mime_type, synthesize_tts_base64
from storage.mongo_store import MongoStore
from domain.doctor_matching import doctor_names_match
from domain.id_normalization import normalize_patient_id
from domain.phone_normalization import (
    has_phone_context,
    normalize_phone_number,
    spoken_phone_digits,
)
from domain.time_normalization import (
    TimeNormalizationResult,
    mentions_clock_time,
    normalize_time_for_slots,
)


APPOINTMENT_WORKFLOW_INTENTS = {
    "book_appointment",
    "reschedule_appointment",
    "check_availability",
}
NULLISH_ENTITY_TEXT = {"null", "none", "n/a", "unknown"}
TURN_IO_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="voice-turn-io")
DOCTOR_CHANGE_TERMS = [
    "نہیں",
    "نهيں",
    "بدل",
    "تبدیل",
    "دوسرے ڈاکٹر",
    "اس کے بجائے",
    "actually",
    "instead",
    "change doctor",
    "another doctor",
    "different doctor",
]


def _requests_doctor_change(transcript: str) -> bool:
    lowered = (transcript or "").lower()
    return any(term.lower() in lowered for term in DOCTOR_CHANGE_TERMS)


def _normalized_doctor_name(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"\b(dr|doctor)\.?\b", "", text)
    return re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", text).strip()


def _without_nullish_entities(entities: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in entities.items()
        if not (
            isinstance(value, str)
            and value.strip().lower() in NULLISH_ENTITY_TEXT
        )
    }


def _explicitly_mentions_patient_name(transcript: str) -> bool:
    lowered = str(transcript or "").lower()
    return any(
        marker in lowered
        for marker in ("میرا نام", "نام ہے", "my name", "name is", "mera naam")
    )


def _allow_doctor_change(
    previous: dict[str, Any],
    incoming: dict[str, Any],
    transcript: str,
) -> bool:
    if not previous.get("_doctor_locked"):
        return True
    if incoming.get("_doctor_locked") is True:
        return True
    previous_id = str(previous.get("doctor_id") or "").strip().upper()
    incoming_id = str(incoming.get("doctor_id") or "").strip().upper()
    previous_name = _normalized_doctor_name(previous.get("doctor_name"))
    incoming_name = _normalized_doctor_name(incoming.get("doctor_name"))

    if not (previous_id or previous_name):
        return True
    if not (incoming_id or incoming_name):
        return True
    if previous_id and incoming_id and previous_id == incoming_id:
        return True
    if previous_name and incoming_name and previous_name == incoming_name:
        return True
    if incoming_name and doctor_names_match(transcript, incoming.get("doctor_name")):
        return True

    normalized_transcript = _normalized_doctor_name(transcript)
    if incoming_name and incoming_name in normalized_transcript:
        return True
    return _requests_doctor_change(transcript)


def _merge_workflow_entities(
    previous: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    """Merge new facts without letting stale alternatives survive.

    A doctor, date, or time mentioned in the current utterance replaces the
    corresponding remembered value as one atomic fact. Unmentioned facts stay
    in the session so short replies such as "10 بجے" retain doctor and date.
    """
    merged = dict(previous)

    incoming_patient_type = str(incoming.get("patient_type") or "").strip().lower()
    previous_patient_type = str(previous.get("patient_type") or "").strip().lower()
    if incoming_patient_type and incoming_patient_type != previous_patient_type:
        for key in (
            "patient_id",
            "patient_name",
            "phone",
            "_registered_patient_valid",
        ):
            merged.pop(key, None)
    if incoming.get("patient_id"):
        for key in ("patient_id", "patient_name", "phone", "_registered_patient_valid"):
            merged.pop(key, None)

    if incoming.get("doctor_id") or incoming.get("doctor_name"):
        merged.pop("doctor_id", None)
        merged.pop("doctor_name", None)
        merged.pop("_offered_doctor_id", None)
        merged.pop("_offered_doctor_name", None)
        # A department inferred for the previous doctor must not select it
        # again when the user changes doctors.
        if not incoming.get("department"):
            merged.pop("department", None)

    if incoming.get("date") or incoming.get("natural_date"):
        merged.pop("date", None)
        merged.pop("natural_date", None)

    if incoming.get("time") or incoming.get("natural_time"):
        merged.pop("time", None)
        merged.pop("natural_time", None)

    merged.update(incoming)
    return merged


def _enrich_entities_for_scheduler(intent, context) -> dict[str, Any]:
    entities = dict(intent.entities)
    if context.selected_doctor and context.doctor_selected_by_user:
        entities["doctor_id"] = context.selected_doctor.get("doctor_id")
        entities["doctor_name"] = context.selected_doctor.get("name")
        entities["department"] = context.selected_doctor.get("department")
        entities.pop("_offered_doctor_id", None)
        entities.pop("_offered_doctor_name", None)
    elif context.selected_doctor:
        # Keep the one doctor associated with the slots just offered. This is
        # internal workflow state, not a permanent user-selected doctor lock.
        entities["_offered_doctor_id"] = context.selected_doctor.get("doctor_id")
        entities["_offered_doctor_name"] = context.selected_doctor.get("name")
    if context.resolved_date:
        entities["date"] = context.resolved_date.strftime("%Y-%m-%d")
    return entities


def _apply_offered_doctor_selection(
    intent_name: str,
    previous_entities: dict[str, Any],
    incoming_entities: dict[str, Any],
) -> dict[str, Any]:
    incoming = dict(incoming_entities)
    offered_doctor_id = previous_entities.get("_offered_doctor_id")
    offered_doctor_name = previous_entities.get("_offered_doctor_name")
    if (
        intent_name == "book_appointment"
        and incoming.get("time")
        and offered_doctor_id
        and not (incoming.get("doctor_id") or incoming.get("doctor_name"))
    ):
        incoming["doctor_id"] = offered_doctor_id
        incoming["doctor_name"] = offered_doctor_name
        incoming["_doctor_locked"] = True
    return incoming


def _can_persist_appointment(intent_name: str, entities: dict[str, Any], context, needs_clarification: bool) -> bool:
    if needs_clarification:
        return False
    if intent_name == "book_appointment":
        if not context.selected_doctor or not context.resolved_date or not entities.get("time"):
            return False
        doctor_id = str(context.selected_doctor.get("doctor_id") or "")
        return str(entities.get("time")) in context.available_slots_by_doctor.get(doctor_id, [])
    if intent_name == "reschedule_appointment":
        if not context.target_appointment or not context.resolved_date or not entities.get("time"):
            return False
        doctor_id = str(context.target_appointment.get("doctor_id") or "")
        return str(entities.get("time")) in context.available_slots_by_doctor.get(doctor_id, [])
    if intent_name == "cancel_appointment":
        return bool(context.target_appointment)
    return False


def _public_doctor(doctor: dict[str, Any] | None) -> dict[str, Any] | None:
    if not doctor:
        return None
    return {
        "name": doctor.get("name"),
        "urdu_name": doctor.get("urdu_name"),
        "status": doctor.get("status"),
    }


def _suggested_slots(slots: list[str]) -> list[str]:
    return list(slots[:2])


def _doctor_display_name(doctor: dict[str, Any] | None) -> str:
    value = str(
        (doctor or {}).get("urdu_name")
        or (doctor or {}).get("name")
        or ""
    ).strip()
    if not value:
        return ""
    return value if value.startswith("ڈاکٹر") else f"ڈاکٹر {value}"


def _time_normalization_slots(
    *,
    previous_entities: dict[str, Any],
    incoming_entities: dict[str, Any],
    intent_name: str,
    transcript: str,
    doctors: list[dict[str, Any]],
    appointments: list[dict[str, Any]],
) -> list[str]:
    previous = dict(previous_entities)
    incoming = dict(incoming_entities)
    for values in (previous, incoming):
        values.pop("time", None)
        values.pop("natural_time", None)
        values.pop("_time_ambiguous_candidates", None)

    probe_entities = _merge_workflow_entities(previous, incoming)
    offered_doctor_id = previous_entities.get("_offered_doctor_id")
    if offered_doctor_id and not probe_entities.get("doctor_id"):
        probe_entities["doctor_id"] = offered_doctor_id
        probe_entities["doctor_name"] = previous_entities.get("_offered_doctor_name")
        probe_entities["_doctor_locked"] = True

    probe_context = build_receptionist_context(
        type("ProbeIntent", (), {"intent": intent_name, "entities": probe_entities})(),
        transcript,
        doctors=doctors,
        appointments=appointments,
    )
    slots = {
        slot
        for doctor_slots in probe_context.available_slots_by_doctor.values()
        for slot in doctor_slots
    }
    if slots:
        return sorted(slots)

    # Without a resolved date, use the relevant doctors' configured schedules
    # to interpret language while keeping database values canonical.
    candidate_doctors = []
    selected_id = str(probe_entities.get("doctor_id") or "")
    if selected_id:
        candidate_doctors = [
            doctor for doctor in doctors
            if str(doctor.get("doctor_id") or "") == selected_id
        ]
    elif probe_context.recommended_doctors:
        candidate_doctors = probe_context.recommended_doctors
    else:
        candidate_doctors = doctors
    return sorted({
        str(slot).strip()
        for doctor in candidate_doctors
        for row in doctor.get("availability") or []
        for slot in row.get("slots") or []
        if str(slot).strip()
    })


def _time_ambiguity_reply(result: TimeNormalizationResult) -> str | None:
    if not result.ambiguous or len(result.candidates) < 2:
        return None
    first, second = result.candidates[:2]
    return (
        f"براہ کرم وقت واضح کریں: {first} صبح یا {second} شام؟"
    )


def _canonical_patient_id(value: Any) -> str:
    return normalize_patient_id(value, allow_digits_only=True) or ""


def _apply_phone_resolution(
    previous_entities: dict[str, Any],
    incoming_entities: dict[str, Any],
    transcript: str,
    *,
    phone_expected: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ground the phone field in the latest utterance and validate it."""
    previous = dict(previous_entities)
    incoming = dict(incoming_entities)
    incoming.pop("phone", None)
    transcript_phone = normalize_phone_number(transcript)
    phone_signal = has_phone_context(transcript)

    if not (phone_expected or phone_signal or transcript_phone):
        # Reject a phone copied by the model from history while retaining an
        # already validated phone in authoritative session state.
        return previous, incoming

    previous.pop("_phone_invalid", None)
    incoming.pop("_phone_invalid", None)

    if transcript_phone:
        # A clearly spoken replacement is accepted even if the agent was not
        # currently asking for the phone.
        previous.pop("phone", None)
        incoming["phone"] = transcript_phone
    elif phone_expected or spoken_phone_digits(transcript):
        # An actual but unusable number attempt invalidates the field. Merely
        # mentioning "phone" later in the call must not erase a valid number
        # that was already captured.
        previous.pop("phone", None)
        incoming["_phone_invalid"] = True
    return previous, incoming


def _hydrate_registered_patient(
    entities: dict[str, Any],
    patients: list[dict[str, Any]],
) -> dict[str, Any]:
    hydrated = dict(entities)
    patient_type = str(hydrated.get("patient_type") or "").strip().lower()
    if not patient_type and (hydrated.get("patient_name") or hydrated.get("phone")):
        patient_type = "new"
        hydrated["patient_type"] = "new"

    if patient_type == "new":
        hydrated.pop("patient_id", None)
        hydrated.pop("_registered_patient_valid", None)
        return hydrated
    if patient_type != "registered":
        return hydrated

    patient_id = _canonical_patient_id(hydrated.get("patient_id"))
    if not patient_id:
        hydrated.pop("patient_id", None)
        hydrated.pop("patient_name", None)
        hydrated.pop("phone", None)
        hydrated.pop("_registered_patient_valid", None)
        return hydrated

    hydrated["patient_id"] = patient_id
    patient = next(
        (
            item for item in patients
            if _canonical_patient_id(item.get("patient_id")) == patient_id
        ),
        None,
    )
    if not patient:
        hydrated.pop("patient_name", None)
        hydrated.pop("phone", None)
        hydrated["_registered_patient_valid"] = False
        return hydrated

    hydrated["patient_name"] = patient.get("name")
    if patient.get("phone"):
        hydrated["phone"] = patient.get("phone")
    else:
        hydrated.pop("phone", None)
    hydrated["_registered_patient_valid"] = True
    return hydrated


def _apply_time_resolution(
    previous_entities: dict[str, Any],
    incoming_entities: dict[str, Any],
    result: TimeNormalizationResult,
) -> tuple[dict[str, Any], dict[str, Any]]:
    previous = dict(previous_entities)
    incoming = dict(incoming_entities)
    if not result.recognized:
        return previous, incoming

    previous.pop("time", None)
    previous.pop("natural_time", None)
    previous.pop("_time_ambiguous_candidates", None)
    incoming.pop("time", None)
    incoming.pop("natural_time", None)
    incoming.pop("_time_ambiguous_candidates", None)
    if result.value:
        incoming["time"] = result.value
    elif result.ambiguous:
        incoming["_time_ambiguous_candidates"] = list(result.candidates)
    return previous, incoming


def _deterministic_booking_reply(
    *,
    intent_name: str,
    missing_fields: list[str],
    appointment_persisted: bool,
    entities: dict[str, Any],
    context,
) -> str | None:
    if intent_name != "book_appointment":
        return None
    if appointment_persisted:
        doctor_name = _doctor_display_name(context.selected_doctor)
        appointment_date = (
            context.resolved_date.strftime("%d-%m-%Y")
            if context.resolved_date
            else str(entities.get("date") or "")
        )
        if entities.get("patient_type") == "registered":
            return (
                f"آپ کا نام {entities.get('patient_name')} ریکارڈ سے تصدیق ہو گیا ہے اور "
                "اپائنٹمنٹ بک کر دی گئی ہے۔ "
                f"خلاصہ: {doctor_name}، تاریخ {appointment_date}، "
                f"وقت {entities.get('time')}، مریض {entities.get('patient_name')}۔"
            )
        return (
            "آپ کی اپائنٹمنٹ کامیابی سے بک ہو گئی ہے۔ "
            f"خلاصہ: {doctor_name}، تاریخ {appointment_date}، "
            f"وقت {entities.get('time')}، مریض {entities.get('patient_name')}، "
            f"فون {entities.get('phone')}۔"
        )
    first_missing = missing_fields[0] if missing_fields else None
    if first_missing == "doctor_name":
        requested_name = str(entities.get("doctor_name") or "").strip()
        if requested_name and context and not context.matched_doctors:
            requested_name = re.sub(r"^(?:Dr\.?|Doctor|ڈاکٹر)\s*", "", requested_name, flags=re.IGNORECASE)
            return (
                f"ڈاکٹر {requested_name} اس ہسپتال میں دستیاب نہیں ہیں۔ "
                "براہ کرم کسی دوسرے ڈاکٹر کا نام بتائیں، یا اپنی تکلیف بتا دیں۔"
            )
        return "براہ کرم ڈاکٹر کا نام بتائیں، یا اپنی تکلیف بتا دیں تاکہ مناسب ڈاکٹر تلاش کر سکوں۔"
    if first_missing == "date":
        return "براہ کرم اپائنٹمنٹ کی تاریخ بتا دیں۔"
    if first_missing == "time":
        doctor_name = _doctor_display_name(context.selected_doctor)
        doctor_id = str((context.selected_doctor or {}).get("doctor_id") or "")
        slots = _suggested_slots(context.available_slots_by_doctor.get(doctor_id, []))
        if slots:
            return (
                f"{doctor_name} کے لیے {slots[0]} یا "
                f"{slots[1] if len(slots) > 1 else slots[0]} دستیاب ہے۔ "
                "براہ کرم ایک وقت منتخب کریں۔"
            )
        return "براہ کرم دستیاب اوقات میں سے ایک وقت منتخب کریں۔"
    if first_missing == "patient_type":
        return "کیا آپ پہلے سے رجسٹرڈ مریض ہیں یا نئے مریض؟"
    if first_missing == "patient_id":
        return "براہ کرم اپنا مریض آئی ڈی بتا دیں۔"
    if first_missing == "valid_patient_id":
        return "یہ مریض آئی ڈی ریکارڈ میں نہیں ملی۔ براہ کرم درست مریض آئی ڈی بتائیں۔"
    if first_missing == "patient_name":
        return "براہ کرم مریض کا مکمل نام بتا دیں۔"
    if first_missing == "phone":
        if entities.get("_phone_invalid"):
            return "فون نمبر واضح نہیں ملا۔ براہ کرم اپنا فون نمبر دوبارہ بتائیں۔"
        return "براہ کرم مریض کا فون نمبر بتا دیں۔"
    if first_missing == "confirmation":
        doctor_name = _doctor_display_name(context.selected_doctor)
        if not doctor_name:
            fallback_name = str(entities.get("doctor_name") or "").strip()
            doctor_name = fallback_name if fallback_name.startswith("ڈاکٹر") else f"ڈاکٹر {fallback_name}"
        appointment_date = (
            context.resolved_date.strftime("%d-%m-%Y")
            if context.resolved_date
            else str(entities.get("date") or "")
        )
        patient_name = str(entities.get("patient_name") or "")
        summary = (
            f"خلاصہ: {doctor_name}، تاریخ {appointment_date}، "
            f"وقت {entities.get('time')}، مریض {patient_name}"
        )
        if entities.get("phone"):
            summary += f"، فون {entities.get('phone')}"
        return f"{summary}۔ کیا آپ اس اپائنٹمنٹ کی حتمی تصدیق کرتے ہیں؟"
    return None


def _deterministic_transaction_reply(
    *,
    intent_name: str,
    missing_fields: list[str],
    appointment_persisted: bool,
    entities: dict[str, Any],
    context,
) -> str | None:
    if intent_name not in {"cancel_appointment", "reschedule_appointment"}:
        return None
    appointment_id = str(entities.get("appointment_id") or "")
    if appointment_persisted and intent_name == "cancel_appointment":
        return f"آپ کی اپائنٹمنٹ {appointment_id} منسوخ کر دی گئی ہے۔"
    if appointment_persisted and intent_name == "reschedule_appointment":
        appointment_date = (
            context.resolved_date.strftime("%d-%m-%Y")
            if context.resolved_date
            else str(entities.get("date") or "")
        )
        return (
            f"آپ کی اپائنٹمنٹ {appointment_id} کو تاریخ {appointment_date}، "
            f"وقت {entities.get('time')} پر منتقل کر دیا گیا ہے۔"
        )
    first_missing = missing_fields[0] if missing_fields else None
    if first_missing == "appointment_id":
        return "براہ کرم اپنی اپائنٹمنٹ آئی ڈی بتا دیں۔"
    if first_missing == "valid_appointment":
        return "یہ اپائنٹمنٹ آئی ڈی ریکارڈ میں نہیں ملی۔ براہ کرم درست اپائنٹمنٹ آئی ڈی بتائیں۔"
    if first_missing == "date":
        return "براہ کرم اپائنٹمنٹ کی نئی تاریخ بتا دیں۔"
    if first_missing == "time":
        target_doctor_id = str((context.target_appointment or {}).get("doctor_id") or "")
        slots = _suggested_slots(context.available_slots_by_doctor.get(target_doctor_id, []))
        if slots:
            return (
                f"{slots[0]} یا {slots[1] if len(slots) > 1 else slots[0]} دستیاب ہے۔ "
                "براہ کرم نیا وقت منتخب کریں۔"
            )
        return "براہ کرم اپائنٹمنٹ کا نیا وقت بتا دیں۔"
    return None


def _deterministic_recommendation_reply(
    *,
    intent_name: str,
    entities: dict[str, Any],
    context,
) -> str | None:
    if (
        intent_name != "check_availability"
        or entities.get("doctor_name")
        or not context.department
    ):
        return None

    doctor = context.selected_doctor
    if not doctor:
        return "اس مسئلے کے لیے اس وقت کوئی متعلقہ ڈاکٹر دستیاب نہیں ہے۔"

    doctor_name = str(doctor.get("urdu_name") or doctor.get("name") or "").strip()
    if not context.resolved_date:
        return (
            f"آپ کی بتائی ہوئی علامات کے لیے {doctor_name} موزوں ہیں۔ "
            "براہِ کرم اپائنٹمنٹ کی تاریخ بتا دیں تاکہ دستیاب وقت دیکھ سکوں۔"
        )

    doctor_id = str(doctor.get("doctor_id") or "")
    slots = _suggested_slots(context.available_slots_by_doctor.get(doctor_id, []))
    date_text = context.resolved_date.strftime("%d-%m-%Y")
    if not slots:
        return (
            f"{doctor_name} آپ کے مسئلے کے لیے موزوں ہیں، لیکن {date_text} کو کوئی وقت دستیاب نہیں ہے۔ "
            "براہِ کرم دوسری تاریخ بتا دیں۔"
        )

    slot_text = " یا ".join(slots)
    return (
        f"آپ کی بتائی ہوئی علامات کے لیے {doctor_name} دستیاب ہیں۔ "
        f"{date_text} کو {slot_text} بجے وقت موجود ہے؛ آپ کون سا وقت بک کرنا چاہتے ہیں؟"
    )


def _deterministic_selected_doctor_unavailable_reply(
    *,
    intent_name: str,
    context,
) -> str | None:
    if (
        intent_name not in {"book_appointment", "check_availability"}
        or not context.doctor_selected_by_user
        or not context.selected_doctor
        or not context.resolved_date
    ):
        return None

    doctor_id = str(context.selected_doctor.get("doctor_id") or "")
    if context.available_slots_by_doctor.get(doctor_id):
        return None

    doctor_name = str(
        context.selected_doctor.get("urdu_name")
        or context.selected_doctor.get("name")
        or ""
    ).strip()
    date_text = context.resolved_date.strftime("%d-%m-%Y")
    return (
        f"{doctor_name} {date_text} کو دستیاب نہیں ہیں۔ "
        "براہِ کرم دوسری تاریخ بتا دیں؛ ڈاکٹر صرف آپ کے کہنے پر تبدیل کیا جائے گا۔"
    )


def process_turn(*, session_id: str, transcript: str, return_tts: bool, store: MongoStore) -> TurnResponse:
    session_future = TURN_IO_EXECUTOR.submit(store.get_session, session_id)
    doctors_future = TURN_IO_EXECUTOR.submit(store.get_doctors)
    appointments_future = TURN_IO_EXECUTOR.submit(store.get_appointments)
    patients_future = TURN_IO_EXECUTOR.submit(store.get_patients)
    session = session_future.result()
    history = session.get("history") or []
    state = session.get("state") or {}
    active_intent = state.get("active_intent")
    last_intent = state.get("last_intent")
    awaiting_final_confirmation = bool(state.get("awaiting_final_confirmation"))
    doctors = doctors_future.result()
    appointments = appointments_future.result()
    patients = patients_future.result()
    intent = detect_intent(
        transcript,
        conversation_history=history,
        active_intent=active_intent,
        doctors=doctors,
        expected_fields=state.get("missing_fields") or [],
        previous_intent=last_intent,
    )
    if (
        intent.entities.get("_department_explicit")
        and intent.intent in {"other", "list_doctors"}
        and (
            active_intent in APPOINTMENT_WORKFLOW_INTENTS
            or last_intent in APPOINTMENT_WORKFLOW_INTENTS
        )
    ):
        intent.intent = "check_availability"
    if (
        active_intent in APPOINTMENT_WORKFLOW_INTENTS
        and intent.intent in {"greeting", "other"}
        and len((transcript or "").split()) <= 5
    ):
        # A short acknowledgement inside an unfinished booking is not a new
        # greeting. Keep the workflow active and re-ask only its missing field.
        intent.intent = active_intent

    # Appointment discovery, availability, and booking are one workflow. Keep
    # its verified facts in this session even if the classifier changes the
    # sub-intent between turns.
    continues_current_task = bool(active_intent and intent.intent == active_intent)
    converts_availability_to_booking = bool(
        intent.intent == "book_appointment"
        and (active_intent == "check_availability" or last_intent in {"check_availability", "book_appointment"})
    )
    continues_appointment_workflow = bool(
        intent.intent in APPOINTMENT_WORKFLOW_INTENTS
        and (active_intent in APPOINTMENT_WORKFLOW_INTENTS or last_intent in APPOINTMENT_WORKFLOW_INTENTS)
    )
    previous_entities = (
        dict(state.get("entities") or {})
        if continues_current_task or converts_availability_to_booking or continues_appointment_workflow
        else {}
    )
    # Confirmation applies only to the current utterance and must never leak
    # from selecting a slot into the later final booking confirmation.
    previous_entities.pop("confirmation", None)
    expected_field = (state.get("missing_fields") or [None])[0]
    raw_incoming_entities = _without_nullish_entities(dict(intent.entities))
    if not (awaiting_final_confirmation and expected_field == "confirmation"):
        # "Yes", a chosen doctor, or a chosen time is only a field selection.
        # It cannot confirm the whole booking before the final summary exists.
        raw_incoming_entities.pop("confirmation", None)
    if expected_field == "phone":
        # Once the name is collected, number speech cannot replace it or
        # switch the new/registered-patient branch.
        raw_incoming_entities.pop("patient_name", None)
        raw_incoming_entities.pop("patient_type", None)
        raw_incoming_entities.pop("patient_id", None)
    elif (
        previous_entities.get("patient_name")
        and raw_incoming_entities.get("patient_name")
        and expected_field != "patient_name"
        and not _explicitly_mentions_patient_name(transcript)
    ):
        raw_incoming_entities.pop("patient_name", None)
    previous_entities, raw_incoming_entities = _apply_phone_resolution(
        previous_entities,
        raw_incoming_entities,
        transcript,
        phone_expected=expected_field == "phone",
    )
    normalization_slots = _time_normalization_slots(
        previous_entities=previous_entities,
        incoming_entities=raw_incoming_entities,
        intent_name=intent.intent,
        transcript=transcript,
        doctors=doctors,
        appointments=appointments,
    )
    ambiguity_candidates = previous_entities.get("_time_ambiguous_candidates") or []
    patient_id_answer = bool(
        raw_incoming_entities.get("patient_id")
        and (state.get("missing_fields") or [None])[0]
        in {"patient_id", "valid_patient_id"}
    )
    phone_answer = bool(
        raw_incoming_entities.get("phone")
        or raw_incoming_entities.get("_phone_invalid")
    )
    if patient_id_answer or phone_answer:
        raw_incoming_entities.pop("time", None)
        raw_incoming_entities.pop("natural_time", None)
        time_resolution = TimeNormalizationResult(recognized=False)
    else:
        time_resolution = normalize_time_for_slots(
            transcript,
            ambiguity_candidates or normalization_slots,
        )
        expected_time_answer = bool(
            ambiguity_candidates
            or (state.get("missing_fields") or [None])[0] == "time"
        )
        if (
            time_resolution.recognized
            and not mentions_clock_time(transcript)
            and not expected_time_answer
        ):
            # A bare period word can describe symptom onset ("since last
            # night") and must not jump ahead of doctor/date selection.
            time_resolution = TimeNormalizationResult(recognized=False)
    previous_entities, raw_incoming_entities = _apply_time_resolution(
        previous_entities,
        raw_incoming_entities,
        time_resolution,
    )
    if time_resolution.recognized:
        if (
            time_resolution.value
            and last_intent == "check_availability"
            and previous_entities.get("_offered_doctor_id")
        ):
            intent.intent = "book_appointment"
    # Selecting a slot from a single doctor's immediately preceding offer also
    # selects that doctor for this booking.
    incoming_entities = _apply_offered_doctor_selection(
        intent.intent,
        previous_entities,
        raw_incoming_entities,
    )
    department_explicit = bool(incoming_entities.pop("_department_explicit", False))
    if department_explicit and incoming_entities.get("_doctor_locked") is not True:
        if previous_entities.get("_doctor_locked") and not _requests_doctor_change(transcript):
            # Repeated symptoms or classifier noise cannot replace a doctor
            # the patient explicitly selected.
            incoming_entities.pop("department", None)
        else:
            previous_entities.pop("doctor_id", None)
            previous_entities.pop("doctor_name", None)
            previous_entities.pop("department", None)
            previous_entities.pop("_doctor_locked", None)
    elif previous_entities.get("_doctor_locked") and not _requests_doctor_change(transcript):
        # A model-inferred department is advisory. Preserve the selected
        # doctor's real department unless the patient asks for a change.
        incoming_entities.pop("department", None)
    if not _allow_doctor_change(previous_entities, incoming_entities, transcript):
        incoming_entities.pop("doctor_id", None)
        incoming_entities.pop("doctor_name", None)
        incoming_entities.pop("department", None)
    intent.entities = _merge_workflow_entities(previous_entities, incoming_entities)
    intent.entities = _hydrate_registered_patient(intent.entities, patients)
    context = build_receptionist_context(
        intent,
        transcript,
        doctors=doctors,
        appointments=appointments,
    )
    missing_fields = get_missing_fields(intent, context)
    selected_doctor_id = str((context.selected_doctor or {}).get("doctor_id") or "")
    selected_doctor_has_no_slots = bool(
        intent.intent in {"book_appointment", "check_availability"}
        and context.doctor_selected_by_user
        and context.resolved_date
        and selected_doctor_id in context.available_slots_by_doctor
        and not context.available_slots_by_doctor[selected_doctor_id]
    )
    if selected_doctor_has_no_slots:
        missing_fields = ["date"]
    if entities_time_ambiguity := intent.entities.get("_time_ambiguous_candidates"):
        missing_fields = ["time", *[field for field in missing_fields if field != "time"]]
    needs_clarification = bool(missing_fields)
    entities = _enrich_entities_for_scheduler(intent, context)
    public_entities = {
        key: value
        for key, value in entities.items()
        if not key.startswith("_")
    }
    intent.entities = public_entities
    can_persist_appointment = False
    next_awaiting_final_confirmation = False

    if intent.intent == "book_appointment" and not missing_fields:
        if awaiting_final_confirmation and entities.get("confirmation") is True:
            can_persist_appointment = _can_persist_appointment(intent.intent, entities, context, False)
        else:
            missing_fields = ["confirmation"]
            needs_clarification = True
            next_awaiting_final_confirmation = True
    else:
        can_persist_appointment = _can_persist_appointment(intent.intent, entities, context, needs_clarification)

    if intent.intent in {"book_appointment", "reschedule_appointment", "cancel_appointment"} and not can_persist_appointment:
        needs_clarification = True
    conversation_ended = intent.intent == "end_conversation"
    if conversation_ended:
        assistant_text = "آپ کا شکریہ۔ خدا حافظ، اپنا خیال رکھیے۔"
    elif intent.intent == "greeting":
        assistant_text = generate_agent_text(intent, transcript, context=context)
    else:
        selected_doctor = context.selected_doctor
        selected_doctor_id = str((selected_doctor or {}).get("doctor_id") or "")
        ambiguity_reply = _time_ambiguity_reply(time_resolution)
        deterministic_reply = _deterministic_booking_reply(
            intent_name=intent.intent,
            missing_fields=missing_fields,
            appointment_persisted=can_persist_appointment,
            entities=entities,
            context=context,
        )
        transaction_reply = _deterministic_transaction_reply(
            intent_name=intent.intent,
            missing_fields=missing_fields,
            appointment_persisted=can_persist_appointment,
            entities=entities,
            context=context,
        )
        recommendation_reply = _deterministic_recommendation_reply(
            intent_name=intent.intent,
            entities=entities,
            context=context,
        )
        unavailable_reply = _deterministic_selected_doctor_unavailable_reply(
            intent_name=intent.intent,
            context=context,
        )
        assistant_text = (
            ambiguity_reply
            or unavailable_reply
            or deterministic_reply
            or transaction_reply
            or recommendation_reply
            or generate_grounded_reply(
            transcript=transcript,
            intent=intent,
            conversation_history=history,
            facts={
                "missing_fields": missing_fields,
                "needs_clarification": needs_clarification,
                "resolved_date": context.resolved_date,
                "selected_doctor": _public_doctor(selected_doctor),
                "matched_doctors": [_public_doctor(doctor) for doctor in context.matched_doctors],
                "recommended_doctors": [_public_doctor(doctor) for doctor in context.recommended_doctors],
                "available_slots": _suggested_slots(
                    context.available_slots_by_doctor.get(selected_doctor_id, [])
                ),
                "doctor_availability": [
                    {
                        "doctor": _public_doctor(doctor),
                        "available_slots": _suggested_slots(
                            context.available_slots_by_doctor.get(
                                str(doctor.get("doctor_id") or ""),
                                [],
                            )
                        ),
                    }
                    for doctor in context.recommended_doctors
                ],
                "requested_doctor_name": entities.get("doctor_name"),
                "requested_doctor_found": bool(
                    context.matched_doctors or context.doctor_selected_by_user
                ),
                "target_appointment_status": (context.target_appointment or {}).get("status"),
                "appointment_persisted": can_persist_appointment,
                "patient_name": entities.get("patient_name"),
                "phone": entities.get("phone"),
                "requested_time": entities.get("time"),
                "awaiting_final_confirmation": next_awaiting_final_confirmation,
                "time_ambiguity": entities_time_ambiguity or None,
            },
        )
        )

    state_entities = (
        {}
        if can_persist_appointment and intent.intent in {
            "book_appointment",
            "reschedule_appointment",
            "cancel_appointment",
        }
        else entities
    )

    def persist_response():
        store.append_session(session_id, "user", transcript)
        store.append_session(session_id, "assistant", assistant_text)
        store.update_session_state(
            session_id,
            active_intent=intent.intent if needs_clarification else None,
            last_intent=intent.intent,
            awaiting_final_confirmation=next_awaiting_final_confirmation,
            entities=state_entities,
            missing_fields=missing_fields,
        )
        store.persist_turn(
            session_id=session_id,
            transcript=transcript,
            intent_name=intent.intent,
            confidence=float(intent.confidence),
            entities=public_entities,
            assistant_text=assistant_text,
            audio_mime=get_tts_mime_type(),
            persist_appointment=can_persist_appointment,
        )
        if conversation_ended:
            store.complete_session(session_id)

    # MongoDB persistence and cloud TTS are independent once reply text is
    # ready. Running them together removes database write time from the voice
    # response's critical path.
    persistence_future = TURN_IO_EXECUTOR.submit(persist_response)
    tts_b64 = None
    mime = None
    tts_error: Exception | None = None
    if return_tts:
        try:
            tts_b64, mime = synthesize_tts_base64(assistant_text)
        except Exception as exc:
            tts_error = exc
    persistence_future.result()
    if tts_error:
        raise tts_error

    return TurnResponse(
        transcript=transcript,
        intent=intent,
        assistant_text=assistant_text,
        needs_clarification=needs_clarification,
        missing_fields=missing_fields,
        conversation_ended=conversation_ended,
        tts_audio_base64=tts_b64,
        audio_mime=mime or "audio/mpeg",
    )


def to_call_log_view(log: dict[str, Any]) -> dict[str, Any]:
    entities = dict(log.get("entities") or {})
    if not entities.get("patient_name") or not entities.get("phone"):
        for turn in reversed(log.get("turns") or []):
            turn_entities = dict(turn.get("entities") or {})
            if not entities.get("patient_name") and turn_entities.get("patient_name"):
                entities["patient_name"] = turn_entities["patient_name"]
            if not entities.get("phone") and turn_entities.get("phone"):
                entities["phone"] = turn_entities["phone"]
            if entities.get("patient_name") and entities.get("phone"):
                break
    return {
        "id": log.get("id"),
        "session_id": log.get("session_id"),
        "patient_name": entities.get("patient_name") or "Unknown Caller",
        "phone": entities.get("phone"),
        "intent": log.get("intent"),
        "confidence": log.get("confidence"),
        "transcript": log.get("transcript"),
        "assistant_text": log.get("assistant_text"),
        "turns": log.get("turns") or [],
        "has_recording": bool(log.get("recording_file_id")),
        "recording_mime": log.get("recording_mime"),
        "recording_size": log.get("recording_size"),
        "recording_duration_seconds": log.get("recording_duration_seconds"),
        "status": log.get("status", "Completed"),
        "created_at": log.get("created_at"),
    }
