from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo
import re

from schemas import IntentResult
from domain.doctor_matching import doctor_name_key, doctor_name_match_score, doctor_names_match
from domain.phone_normalization import is_valid_phone_number
from domain.symptom_routing import DEPARTMENT_SYMPTOMS, infer_department_from_symptoms


APP_TZ = ZoneInfo("Asia/Karachi")
WEEK_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
INITIAL_GREETING_URDU = (
    "السلام علیکم! میں شفا ہسپتال کا وائس اسسٹنٹ ہوں۔ "
    "آپ ڈاکٹر کی دستیابی یا اپائنٹمنٹ کے بارے میں بتا سکتے ہیں۔"
)

FIELD_LABELS_URDU = {
    "doctor_name": "ڈاکٹر کا نام یا مسئلہ",
    "department": "شعبہ",
    "date": "اپائنٹمنٹ کی تاریخ",
    "time": "اپائنٹمنٹ کا وقت",
    "appointment_id": "اپائنٹمنٹ آئی ڈی",
    "valid_appointment": "درست اپائنٹمنٹ آئی ڈی",
}

URDU_DATE_NAMES = {
    "aaj": "آج",
    "today": "آج",
    "kal": "کل",
    "tomorrow": "کل",
    "parson": "پرسوں",
}


@dataclass
class ReceptionistContext:
    now: datetime
    doctors: list[dict[str, Any]]
    appointments: list[dict[str, Any]] = field(default_factory=list)
    matched_doctors: list[dict[str, Any]] = field(default_factory=list)
    recommended_doctors: list[dict[str, Any]] = field(default_factory=list)
    duplicate_name: bool = False
    selected_doctor: dict[str, Any] | None = None
    doctor_selected_by_user: bool = False
    target_appointment: dict[str, Any] | None = None
    resolved_date: date | None = None
    available_slots_by_doctor: dict[str, list[str]] = field(default_factory=dict)
    department: str | None = None
    reason: str | None = None


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    text = _clean_text(value).lower()
    text = re.sub(r"\b(dr|doctor)\.?\b", "", text)
    text = text.replace("ڈاکٹر", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _contains_any(text: str, needles: list[str]) -> bool:
    lowered = text.lower()
    return any(needle.lower() in lowered for needle in needles)


def _doctor_label(doctor: dict[str, Any]) -> str:
    parts = [_clean_text(doctor.get("name"))]
    if doctor.get("department"):
        parts.append(_clean_text(doctor.get("department")))
    if doctor.get("qualification"):
        parts.append(_clean_text(doctor.get("qualification")))
    return "، ".join(part for part in parts if part)


def _format_doctor_list(doctors: list[dict[str, Any]], limit: int = 4) -> str:
    labels = [_doctor_label(doctor) for doctor in doctors[:limit]]
    if not labels:
        return "اس وقت کوئی ڈاکٹر موجود نہیں"
    return "؛ ".join(labels)


def _parse_date_from_entities(entities: dict[str, Any], now: datetime) -> date | None:
    raw_date = _clean_text(entities.get("date"))
    if raw_date:
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d-%m-%y"):
            try:
                return datetime.strptime(raw_date.replace("/", "-"), fmt).date()
            except ValueError:
                continue

    natural = _clean_text(entities.get("natural_date")).lower()
    if natural in {"aaj", "today"}:
        return now.date()
    if natural in {"kal", "tomorrow"}:
        return now.date() + timedelta(days=1)
    if natural in {"parson"}:
        return now.date() + timedelta(days=2)
    return None


def _format_date_for_user(target: date | None, entities: dict[str, Any]) -> str:
    if not target:
        return "آپ کی بتائی ہوئی تاریخ"
    natural = _clean_text(entities.get("natural_date")).lower()
    if natural in URDU_DATE_NAMES:
        return URDU_DATE_NAMES[natural]
    return target.strftime("%Y-%m-%d")


def _booked_slots(appointments: list[dict[str, Any]], doctor_id: str, target: date) -> set[str]:
    prefix = target.strftime("%Y-%m-%d")
    booked: set[str] = set()
    for appointment in appointments:
        if appointment.get("doctor_id") != doctor_id:
            continue
        if str(appointment.get("status") or "").lower() == "cancelled":
            continue
        scheduled_for = _clean_text(appointment.get("scheduled_for"))
        if not scheduled_for.startswith(prefix):
            continue
        parts = scheduled_for.split()
        if len(parts) >= 2:
            booked.add(parts[1])
    return booked


def _available_slots(doctor: dict[str, Any], target: date, now: datetime, appointments: list[dict[str, Any]]) -> list[str]:
    weekday = WEEK_DAYS[target.weekday()]
    slots: list[str] = []
    for row in doctor.get("availability") or []:
        if row.get("day") == weekday:
            slots = [str(slot).strip() for slot in row.get("slots") or [] if str(slot).strip()]
            break

    booked = _booked_slots(appointments, _clean_text(doctor.get("doctor_id")), target)
    available = [slot for slot in sorted(slots) if slot not in booked]
    if target == now.date():
        available = [slot for slot in available if slot > now.strftime("%H:%M")]
    return available


def _infer_department(transcript: str, entities: dict[str, Any], doctors: list[dict[str, Any]]) -> str | None:
    explicit = _clean_text(entities.get("department"))
    if explicit:
        return explicit

    if symptom_department := infer_department_from_symptoms(transcript):
        return symptom_department

    searchable = transcript.lower()
    known_departments = {_clean_text(doctor.get("department")) for doctor in doctors if doctor.get("department")}
    for department in known_departments:
        if department and department.lower() in searchable:
            return department
    return None


def _recommend_doctors(department: str | None, transcript: str, doctors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not department:
        return []

    department_norm = _norm(department)
    text_norm = _norm(transcript)
    matches: list[dict[str, Any]] = []
    for doctor in doctors:
        if _norm(doctor.get("status")) != "available":
            continue
        haystack = " ".join(
            _norm(doctor.get(field)) for field in ["department", "specialization", "qualification", "name"]
        )
        if department_norm and department_norm in haystack:
            matches.append(doctor)
        elif any(_norm(symptom) in text_norm for symptom in DEPARTMENT_SYMPTOMS.get(department, [])):
            if department_norm in haystack:
                matches.append(doctor)
    return sorted(matches, key=lambda d: (0 if _norm(d.get("status")) == "available" else 1, _norm(d.get("name"))))


def _match_named_doctors(doctor_name: str, doctors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not doctor_name:
        return []
    scored_matches: list[tuple[float, dict[str, Any]]] = []
    for doctor in doctors:
        aliases = [doctor.get("name"), doctor.get("urdu_name")]
        score = max(
            (
                doctor_name_match_score(doctor_name, alias)
                for alias in aliases
                if alias
            ),
            default=0.0,
        )
        if score >= 0.78:
            scored_matches.append((score, doctor))
    if not scored_matches:
        return []
    best_score = max(score for score, _ in scored_matches)
    return [
        doctor
        for score, doctor in scored_matches
        if abs(score - best_score) < 1e-9
    ]


def _match_doctor_id(doctor_id: str, doctors: list[dict[str, Any]]) -> dict[str, Any] | None:
    target = _clean_text(doctor_id).upper()
    if not target:
        return None
    for doctor in doctors:
        if _clean_text(doctor.get("doctor_id")).upper() == target:
            return doctor
    return None


def _select_canonical_named_doctor(
    matches: list[dict[str, Any]],
    *,
    resolved_date: date | None,
    now: datetime,
    appointments: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]

    # Duplicate imports can represent the same public doctor under multiple
    # departments. Department is an internal distinction and should not be
    # pushed onto the patient. Prefer the record that actually has slots for
    # the requested date. Preserve catalog order when otherwise tied; an
    # internal ID must never decide which doctor the caller meant.
    normalized_names = {doctor_name_key(doctor.get("name")) for doctor in matches}
    if len(normalized_names) != 1:
        return None

    ranked = list(matches)
    if resolved_date:
        with_slots = [
            doctor
            for doctor in ranked
            if _available_slots(doctor, resolved_date, now, appointments)
        ]
        if with_slots:
            ranked = with_slots
    available = [
        doctor for doctor in ranked
        if _norm(doctor.get("status")) == "available"
    ]
    return (available or ranked)[0]


def _target_appointment(entities: dict[str, Any], appointments: list[dict[str, Any]]) -> dict[str, Any] | None:
    appointment_id = _clean_text(entities.get("appointment_id")).upper()
    if not appointment_id:
        return None
    for appointment in appointments:
        if _clean_text(appointment.get("appointment_id")).upper() == appointment_id:
            return appointment
    return None


def build_receptionist_context(
    intent: IntentResult,
    transcript: str,
    *,
    doctors: list[dict[str, Any]],
    appointments: list[dict[str, Any]],
    now: datetime | None = None,
) -> ReceptionistContext:
    now = now or datetime.now(APP_TZ)
    entities = intent.entities
    department = _infer_department(transcript, entities, doctors)
    selected_doctor = _match_doctor_id(_clean_text(entities.get("doctor_id")), doctors)
    matched_doctors = _match_named_doctors(_clean_text(entities.get("doctor_name")), doctors)
    if selected_doctor:
        matched_doctors = [selected_doctor]
    recommended_doctors = _recommend_doctors(department, transcript, doctors)
    resolved_date = _parse_date_from_entities(entities, now)
    target_appointment = _target_appointment(entities, appointments)
    doctor_selected_by_user = False
    if not selected_doctor:
        selected_doctor = _select_canonical_named_doctor(
            matched_doctors,
            resolved_date=resolved_date,
            now=now,
            appointments=appointments,
        )
    if selected_doctor:
        lock_marker = entities.get("_doctor_locked")
        doctor_selected_by_user = bool(
            lock_marker is True
            or (lock_marker is None and entities.get("doctor_name"))
            or entities.get("doctor_id")
        )

    slots: dict[str, list[str]] = {}
    if resolved_date:
        candidates = [selected_doctor] if selected_doctor else (matched_doctors or recommended_doctors)
        if target_appointment and target_appointment.get("doctor_id"):
            appointment_doctor = _match_doctor_id(_clean_text(target_appointment.get("doctor_id")), doctors)
            if appointment_doctor and appointment_doctor not in candidates:
                candidates = [appointment_doctor, *candidates]
        for doctor in candidates:
            if not doctor:
                continue
            doctor_id = _clean_text(doctor.get("doctor_id"))
            slots[doctor_id] = _available_slots(doctor, resolved_date, now, appointments)
        if not selected_doctor:
            available_recommendations = [
                doctor
                for doctor in recommended_doctors
                if slots.get(_clean_text(doctor.get("doctor_id")))
            ]
            if available_recommendations:
                selected_doctor = available_recommendations[0]
    elif not selected_doctor and recommended_doctors:
        selected_doctor = recommended_doctors[0]

    return ReceptionistContext(
        now=now,
        doctors=doctors,
        appointments=appointments,
        matched_doctors=matched_doctors,
        recommended_doctors=recommended_doctors,
        duplicate_name=bool(len(matched_doctors) > 1 and not selected_doctor),
        selected_doctor=selected_doctor,
        doctor_selected_by_user=doctor_selected_by_user,
        target_appointment=target_appointment,
        resolved_date=resolved_date,
        available_slots_by_doctor=slots,
        department=department,
        reason=_clean_text(entities.get("reason")) or transcript,
    )


def get_missing_fields(intent: IntentResult, context: ReceptionistContext | None = None) -> list[str]:
    entities = intent.entities
    intent_name = intent.intent

    def missing_date() -> bool:
        return not (entities.get("date") or entities.get("natural_date"))

    def missing_time() -> bool:
        return not entities.get("time")

    missing: list[str] = []
    if intent_name == "book_appointment":
        if context and context.duplicate_name:
            missing.append("department")
        elif entities.get("doctor_name") and context and not context.selected_doctor:
            missing.append("doctor_name")
        elif not (context and context.selected_doctor and context.doctor_selected_by_user):
            missing.append("doctor_name")
        if missing_date():
            missing.append("date")
        if missing_time():
            missing.append("time")
        patient_type = _clean_text(entities.get("patient_type")).lower()
        if not patient_type and (entities.get("patient_name") or entities.get("phone")):
            patient_type = "new"
        if patient_type not in {"registered", "new"}:
            missing.append("patient_type")
        elif patient_type == "registered":
            if not entities.get("patient_id"):
                missing.append("patient_id")
            elif entities.get("_registered_patient_valid") is not True:
                missing.append("valid_patient_id")
        else:
            if not entities.get("patient_name"):
                missing.append("patient_name")
            if not is_valid_phone_number(entities.get("phone")):
                missing.append("phone")
    elif intent_name == "check_availability":
        if context and context.duplicate_name:
            missing.append("department")
        elif entities.get("doctor_name") and context and not context.matched_doctors:
            missing.append("doctor_name")
        elif not (entities.get("doctor_name") or entities.get("department") or (context and context.recommended_doctors)):
            missing.append("doctor_name")
        if missing_date():
            missing.append("date")
    elif intent_name == "reschedule_appointment":
        if not entities.get("appointment_id"):
            missing.append("appointment_id")
        elif context and not context.target_appointment:
            missing.append("valid_appointment")
        if missing_date():
            missing.append("date")
        if missing_time():
            missing.append("time")
    elif intent_name == "cancel_appointment":
        if not entities.get("appointment_id"):
            missing.append("appointment_id")
        elif context and not context.target_appointment:
            missing.append("valid_appointment")
    return missing


def generate_agent_text(
    intent: IntentResult,
    transcript: str,
    *,
    missing_fields: list[str] | None = None,
    context: ReceptionistContext | None = None,
) -> str:
    if intent.intent != "greeting":
        raise ValueError("Non-greeting responses must be generated by the grounded LLM reply service.")
    return INITIAL_GREETING_URDU
