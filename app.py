from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Any, Literal
import base64
import binascii
import csv
import io
import re
import secrets
from pymongo.errors import DuplicateKeyError

from config import ADMIN_SIGNUP_CODE, FRONTEND_ORIGIN, MONGODB_DB_NAME, MONGODB_URI
from domain.auth_validation import (
    AuthValidationError,
    normalize_admin_name,
    normalize_admin_username,
    validate_admin_password,
    validate_login_password,
)
from schemas import GreetingResponse, TurnResponse
from services.asr_service import get_asr_status
from services.asr_service import transcribe_audio_bytes
from services.dialogue_service import INITIAL_GREETING_URDU
from services.llm_service import get_llm_status
from services.tts_service import get_tts_mime_type, get_tts_status, synthesize_tts_base64
from services.turn_service import process_turn, to_call_log_view
from storage.mongo_store import MongoStore

app = FastAPI(title="Shifa Voice Agent")
store = MongoStore(MONGODB_URI, MONGODB_DB_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TextTurnRequest(BaseModel):
    transcript: str
    session_id: str = "default"
    return_tts: bool = True


class AudioTurnRequest(BaseModel):
    audio_base64: str
    filename: str = "audio.wav"
    session_id: str = "default"
    return_tts: bool = True


@app.get("/voice/greeting", response_model=GreetingResponse)
def voice_greeting():
    audio_base64 = None
    audio_mime = get_tts_mime_type()
    try:
        audio_base64, audio_mime = synthesize_tts_base64(INITIAL_GREETING_URDU)
    except Exception:
        # The frontend can use its browser Urdu voice when cloud TTS is
        # temporarily unavailable, so greeting text should still be returned.
        pass
    return GreetingResponse(
        assistant_text=INITIAL_GREETING_URDU,
        tts_audio_base64=audio_base64,
        audio_mime=audio_mime,
    )


class DoctorAvailabilitySlot(BaseModel):
    day: Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    slots: list[str] = Field(default_factory=list)
    timeslots: list[str] | None = None

    @model_validator(mode="before")
    @classmethod
    def merge_legacy_timeslots(cls, data: Any) -> Any:
        if isinstance(data, dict) and "slots" not in data and "timeslots" in data:
            copied = dict(data)
            copied["slots"] = copied.get("timeslots") or []
            return copied
        return data

    @field_validator("slots")
    @classmethod
    def validate_slots(cls, value: list[str]) -> list[str]:
        slot_pattern = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
        for slot in value:
            if not isinstance(slot, str) or not slot_pattern.match(slot.strip()):
                raise ValueError(f"Invalid slot format: {slot}. Expected HH:mm.")
        return value


class DoctorCreateRequest(BaseModel):
    name: str
    urdu_name: str | None = None
    department: str | None = None
    specialization: str | None = None
    qualification: str | None = None
    status: str = "Available"
    availability: list[DoctorAvailabilitySlot] = Field(default_factory=list)


class DoctorUpdateRequest(BaseModel):
    name: str | None = None
    urdu_name: str | None = None
    department: str | None = None
    specialization: str | None = None
    qualification: str | None = None
    status: str | None = None
    availability: list[DoctorAvailabilitySlot] | None = None


class DoctorBulkImportError(BaseModel):
    row: int
    error: str


class DoctorBulkImportResponse(BaseModel):
    imported_count: int
    failed_count: int
    doctors: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[DoctorBulkImportError] = Field(default_factory=list)


class PatientCreateRequest(BaseModel):
    name: str
    phone: str | None = None
    conditions: list[str] = Field(default_factory=list)
    status: str = "Active"


class PatientUpdateRequest(BaseModel):
    name: str | None = None
    phone: str | None = None
    conditions: list[str] | None = None
    status: str | None = None


class AdminSignupRequest(BaseModel):
    name: str
    username: str
    password: str
    code: str


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminForgotPasswordRequest(BaseModel):
    username: str
    code: str
    new_password: str


class AdminProfileUpdateRequest(BaseModel):
    current_username: str
    name: str
    username: str


class AdminChangePasswordRequest(BaseModel):
    username: str
    old_password: str
    new_password: str


class NewAppointmentPatientPayload(BaseModel):
    name: str
    phone: str | None = None
    conditions: list[str] = Field(default_factory=list)
    status: str = "Active"


class ManualAppointmentRequest(BaseModel):
    patient_type: Literal["new", "old"]
    patient_id: str | None = None
    patient: NewAppointmentPatientPayload | None = None
    doctor_id: str
    appointment_date: str
    slot: str
    reason: str | None = None


class AppointmentUpdateRequest(BaseModel):
    doctor_id: str | None = None
    appointment_date: str | None = None
    slot: str | None = None
    reason: str | None = None
    status: str | None = None


@app.get("/health")
def health():
    return {"status": "ok", "mongo_connected": store.ping()}


@app.post("/voice/turn", response_model=TurnResponse)
async def voice_turn(
    audio: UploadFile = File(...),
    session_id: str = Form("default"),
    return_tts: bool = Form(True),
):
    audio_bytes = await audio.read()

    transcript = transcribe_audio_bytes(audio_bytes, filename=audio.filename or "audio.wav")
    resp = process_turn(session_id=session_id, transcript=transcript, return_tts=return_tts, store=store)
    return JSONResponse(resp.model_dump())


@app.post("/voice/text-turn", response_model=TurnResponse)
def voice_text_turn(payload: TextTurnRequest):
    resp = process_turn(
        session_id=payload.session_id,
        transcript=payload.transcript,
        return_tts=payload.return_tts,
        store=store,
    )
    return JSONResponse(resp.model_dump())


@app.post("/voice/audio-turn", response_model=TurnResponse)
def voice_audio_turn(payload: AudioTurnRequest):
    try:
        audio_bytes = base64.b64decode(payload.audio_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="audio_base64 must be valid base64 audio.")

    transcript = transcribe_audio_bytes(audio_bytes, filename=payload.filename or "audio.wav")
    resp = process_turn(
        session_id=payload.session_id,
        transcript=transcript,
        return_tts=payload.return_tts,
        store=store,
    )
    return JSONResponse(resp.model_dump())


@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    return store.get_session(session_id)


@app.post("/sessions/{session_id}/complete")
def complete_session(session_id: str):
    store.complete_session(session_id)
    return {"session_id": session_id, "status": "Completed"}


@app.get("/dashboard/summary")
def dashboard_summary():
    summary = store.get_dashboard_summary()
    summary["recent_calls"] = [
        to_call_log_view(log) for log in summary.get("recent_calls", [])
    ]
    return summary


@app.get("/doctors")
def doctors():
    return store.get_doctors()


@app.post("/doctors")
def create_doctor(payload: DoctorCreateRequest):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Doctor name is required.")
    return store.create_doctor(payload.model_dump())


@app.post("/doctors/bulk-import", response_model=DoctorBulkImportResponse)
async def bulk_import_doctors(file: UploadFile = File(...)):
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="CSV file is empty.")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded.")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file must include a header row.")

    normalized_headers = {str(header or "").strip().lower(): header for header in reader.fieldnames}
    column_aliases = {
        "name": ["name", "doctor_name", "doctor name"],
        "urdu_name": ["urdu_name", "urdu name", "doctor_name_urdu", "doctor name urdu"],
        "department": ["department"],
        "specialization": ["specialization", "specialisation", "specialty", "speciality"],
        "qualification": ["qualification", "qualifications", "degree", "degrees"],
        "status": ["status"],
    }
    if not any(alias in normalized_headers for alias in column_aliases["name"]):
        raise HTTPException(status_code=400, detail="CSV must include a 'name' or 'doctor name' column.")

    valid_statuses = {"available": "Available", "busy": "Busy", "on leave": "On Leave"}
    doctors: list[dict[str, Any]] = []
    errors: list[DoctorBulkImportError] = []

    def value(row: dict[str, str], column: str) -> str:
        header = None
        for alias in column_aliases[column]:
            if alias in normalized_headers:
                header = normalized_headers[alias]
                break
        return str(row.get(header) or "").strip() if header else ""

    for row_number, row in enumerate(reader, start=2):
        if not any(str(item or "").strip() for item in row.values()):
            continue

        name = value(row, "name")
        if not name:
            errors.append(DoctorBulkImportError(row=row_number, error="Doctor name is required."))
            continue

        status_raw = value(row, "status") or "Available"
        status = valid_statuses.get(status_raw.lower())
        if not status:
            errors.append(
                DoctorBulkImportError(
                    row=row_number,
                    error="Status must be Available, Busy, or On Leave.",
                )
            )
            continue

        payload = {
            "name": name,
            "urdu_name": value(row, "urdu_name") or None,
            "department": value(row, "department") or None,
            "specialization": value(row, "specialization") or None,
            "qualification": value(row, "qualification") or None,
            "status": status,
            "availability": [],
        }
        try:
            validated = DoctorCreateRequest(**payload)
            doctors.append(store.create_doctor(validated.model_dump()))
        except Exception as exc:
            errors.append(DoctorBulkImportError(row=row_number, error=str(exc)))

    if not doctors and errors:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "No doctors were imported.",
                "errors": [error.model_dump() for error in errors],
            },
        )

    return DoctorBulkImportResponse(
        imported_count=len(doctors),
        failed_count=len(errors),
        doctors=doctors,
        errors=errors,
    )


@app.put("/doctors/{doctor_id}")
def update_doctor(doctor_id: str, payload: DoctorUpdateRequest):
    updated = store.update_doctor(doctor_id, payload.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Doctor not found.")
    return updated


@app.delete("/doctors/{doctor_id}")
def delete_doctor(doctor_id: str):
    deleted = store.delete_doctor(doctor_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Doctor not found.")
    return {"deleted": True}


@app.get("/patients")
def patients():
    return store.get_patients()


@app.post("/patients")
def create_patient(payload: PatientCreateRequest):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Patient name is required.")
    return store.create_patient(payload.model_dump())


@app.put("/patients/{patient_id}")
def update_patient(patient_id: str, payload: PatientUpdateRequest):
    updated = store.update_patient(patient_id, payload.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Patient not found.")
    return updated


@app.delete("/patients/{patient_id}")
def delete_patient(patient_id: str):
    deleted = store.delete_patient(patient_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Patient not found.")
    return {"deleted": True}


@app.get("/patients/{patient_id}/appointments")
def patient_appointments(patient_id: str):
    docs = store.get_patient_appointments(patient_id)
    doctor_map = {d["doctor_id"]: d for d in store.get_doctors()}
    output: list[dict[str, Any]] = []
    for appt in docs:
        doctor = doctor_map.get(appt.get("doctor_id"))
        output.append(
            {
                **appt,
                "doctor_name": doctor.get("name") if doctor else None,
            }
        )
    return output


@app.get("/appointments")
def appointments():
    docs = store.get_appointments()
    doctor_map = {d["doctor_id"]: d for d in store.get_doctors()}
    patient_map = {p["patient_id"]: p for p in store.get_patients()}
    output: list[dict[str, Any]] = []
    for appt in docs:
        doctor = doctor_map.get(appt.get("doctor_id"))
        patient = patient_map.get(appt.get("patient_id"))
        output.append(
            {
                **appt,
                "doctor_name": doctor.get("name") if doctor else None,
                "patient_name": patient.get("name") if patient else None,
                "patient_phone": patient.get("phone") if patient else None,
            }
        )
    return output


@app.post("/appointments/manual")
def create_manual_appointment(payload: ManualAppointmentRequest):
    if payload.patient_type == "new" and payload.patient is None:
        raise HTTPException(status_code=400, detail="Patient details are required for new patient flow.")
    if payload.patient_type == "old" and not (payload.patient_id or "").strip():
        raise HTTPException(status_code=400, detail="Patient ID is required for old patient flow.")
    try:
        created = store.create_manual_appointment(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    doctor_map = {d["doctor_id"]: d for d in store.get_doctors()}
    patient_map = {p["patient_id"]: p for p in store.get_patients()}
    doctor = doctor_map.get(created.get("doctor_id"))
    patient = patient_map.get(created.get("patient_id"))
    return {
        **created,
        "doctor_name": doctor.get("name") if doctor else None,
        "patient_name": patient.get("name") if patient else None,
        "patient_phone": patient.get("phone") if patient else None,
    }


@app.put("/appointments/{appointment_id}")
def update_appointment(appointment_id: str, payload: AppointmentUpdateRequest):
    try:
        updated = store.update_appointment(appointment_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not updated:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    doctor_map = {d["doctor_id"]: d for d in store.get_doctors()}
    patient_map = {p["patient_id"]: p for p in store.get_patients()}
    doctor = doctor_map.get(updated.get("doctor_id"))
    patient = patient_map.get(updated.get("patient_id"))
    return {
        **updated,
        "doctor_name": doctor.get("name") if doctor else None,
        "patient_name": patient.get("name") if patient else None,
        "patient_phone": patient.get("phone") if patient else None,
    }


@app.post("/appointments/{appointment_id}/cancel")
def cancel_appointment(appointment_id: str):
    updated = store.cancel_appointment(appointment_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    return {"ok": True, "appointment": updated}


@app.delete("/appointments/{appointment_id}")
def delete_appointment(appointment_id: str):
    deleted = store.delete_appointment(appointment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    return {"ok": True}


@app.get("/call-logs")
def call_logs(limit: int = 100):
    logs = store.get_call_logs(limit=limit)
    return [to_call_log_view(log) for log in logs]


@app.post("/call-logs/{session_id}/recording")
async def upload_call_recording(
    session_id: str,
    recording: UploadFile = File(...),
    duration_seconds: float | None = Form(default=None),
):
    content_type = recording.content_type or "audio/webm"
    if not content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Recording must be an audio file.")
    audio_bytes = await recording.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Call recording is empty.")
    try:
        recording_id = store.save_call_recording(
            session_id=session_id,
            audio_bytes=audio_bytes,
            content_type=content_type,
            filename=recording.filename or f"{session_id}.webm",
            duration_seconds=duration_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "session_id": session_id,
        "recording_id": recording_id,
        "size": len(audio_bytes),
        "content_type": content_type,
    }


@app.get("/call-logs/{session_id}/recording")
def stream_call_recording(session_id: str, request: Request):
    opened = store.open_call_recording(session_id)
    if not opened:
        raise HTTPException(status_code=404, detail="Call recording not found.")
    recording_stream, content_type = opened

    total_size = int(recording_stream.length)
    range_header = request.headers.get("range")
    start = 0
    end = total_size - 1
    status_code = 200

    if range_header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
        if not match:
            recording_stream.close()
            raise HTTPException(
                status_code=416,
                detail="Invalid recording byte range.",
                headers={"Content-Range": f"bytes */{total_size}"},
            )
        start_text, end_text = match.groups()
        if not start_text and not end_text:
            recording_stream.close()
            raise HTTPException(
                status_code=416,
                detail="Invalid recording byte range.",
                headers={"Content-Range": f"bytes */{total_size}"},
            )
        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else end
        else:
            suffix_length = int(end_text)
            start = max(total_size - suffix_length, 0)
        if start >= total_size or start > end:
            recording_stream.close()
            raise HTTPException(
                status_code=416,
                detail="Recording byte range is outside the file.",
                headers={"Content-Range": f"bytes */{total_size}"},
            )
        end = min(end, total_size - 1)
        recording_stream.seek(start)
        status_code = 206

    content_length = max(end - start + 1, 0)

    def chunks():
        remaining = content_length
        try:
            while remaining > 0:
                chunk = recording_stream.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
        finally:
            recording_stream.close()

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
        "Content-Disposition": f'inline; filename="{session_id}.webm"',
    }
    if status_code == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"

    return StreamingResponse(
        chunks(),
        media_type=content_type,
        status_code=status_code,
        headers=headers,
    )


@app.get("/system-monitoring")
def system_monitoring():
    database_connected = store.ping()
    asr_status = get_asr_status()
    llm_status = get_llm_status()
    tts_status = get_tts_status()
    database_status = {
        "name": "Database",
        "status": "Active" if database_connected else "Down",
        "detail": "MongoDB ping succeeded." if database_connected else "MongoDB ping failed.",
    }

    services = [
        {"name": "ASR Service", **asr_status},
        {"name": "LLM Service", **llm_status},
        {"name": "TTS Service", **tts_status},
        database_status,
    ]
    active_calls = 0
    if database_connected:
        try:
            active_calls = store.call_logs.count_documents({"status": "Completed"})
        except Exception:
            database_connected = False
            services[-1] = {
                "name": "Database",
                "status": "Down",
                "detail": "MongoDB call log query failed.",
            }

    has_down_service = any(service["status"] == "Down" for service in services)
    has_ready_service = any(service["status"] == "Ready" for service in services)
    overall_status = "All Systems Operational"
    if has_down_service:
        overall_status = "Degraded"
    elif has_ready_service:
        overall_status = "Ready"

    return {
        "overall_status": overall_status,
        "database_connected": database_connected,
        "active_calls": active_calls,
        "services": services,
    }


@app.post("/auth/signup")
def auth_signup(payload: AdminSignupRequest):
    if not secrets.compare_digest(payload.code.strip(), ADMIN_SIGNUP_CODE):
        raise HTTPException(status_code=403, detail="Invalid signup code.")
    try:
        name = normalize_admin_name(payload.name)
        username = normalize_admin_username(payload.username)
        password = validate_admin_password(payload.password, username=username)
    except AuthValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        user = store.create_admin_user(name=name, username=username, password=password)
        return {"ok": True, "user": user}
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Username already exists.")


@app.post("/auth/login")
def auth_login(payload: AdminLoginRequest):
    try:
        username = normalize_admin_username(payload.username)
        password = validate_login_password(payload.password)
    except AuthValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    user = store.authenticate_admin(username=username, password=password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return {"ok": True, "user": user}


@app.post("/auth/forgot-password")
def auth_forgot_password(payload: AdminForgotPasswordRequest):
    if not secrets.compare_digest(payload.code.strip(), ADMIN_SIGNUP_CODE):
        raise HTTPException(status_code=403, detail="Invalid reset code.")
    try:
        username = normalize_admin_username(payload.username)
        new_password = validate_admin_password(payload.new_password, username=username)
    except AuthValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    updated = store.reset_admin_password(username=username, new_password=new_password)
    if not updated:
        raise HTTPException(status_code=404, detail="Username not found.")
    return {"ok": True}


@app.get("/auth/profile/{username}")
def auth_profile(username: str):
    try:
        normalized_username = normalize_admin_username(username)
    except AuthValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    user = store.get_admin_user(username=normalized_username)
    if not user:
        raise HTTPException(status_code=404, detail="Administrator not found.")
    return {"ok": True, "user": user}


@app.put("/auth/profile")
def auth_update_profile(payload: AdminProfileUpdateRequest):
    try:
        current_username = normalize_admin_username(payload.current_username)
        name = normalize_admin_name(payload.name)
        username = normalize_admin_username(payload.username)
    except AuthValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        user = store.update_admin_user(
            current_username=current_username,
            name=name,
            username=username,
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Username already exists.")
    if not user:
        raise HTTPException(status_code=404, detail="Administrator not found.")
    return {"ok": True, "user": user}


@app.post("/auth/change-password")
def auth_change_password(payload: AdminChangePasswordRequest):
    try:
        username = normalize_admin_username(payload.username)
        old_password = validate_login_password(payload.old_password)
        new_password = validate_admin_password(
            payload.new_password,
            username=username,
        )
    except AuthValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if secrets.compare_digest(old_password, new_password):
        raise HTTPException(
            status_code=400,
            detail="New password must be different from the current password.",
        )
    if not store.authenticate_admin(username=username, password=old_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    if not store.reset_admin_password(username=username, new_password=new_password):
        raise HTTPException(status_code=404, detail="Administrator not found.")
    return {"ok": True}


@app.post("/auth/profile-picture")
async def auth_profile_picture(
    username: str = Form(...),
    picture: UploadFile = File(...),
):
    try:
        normalized_username = normalize_admin_username(username)
    except AuthValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    content_type = (picture.content_type or "").lower()
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail="Profile picture must be a JPG, PNG, or WebP image.",
        )
    image_bytes = await picture.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Profile picture is empty.")
    if len(image_bytes) > 2 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="Profile picture must not exceed 2 MB.",
        )
    profile_picture = (
        f"data:{content_type};base64,"
        f"{base64.b64encode(image_bytes).decode('ascii')}"
    )
    user = store.set_admin_profile_picture(
        username=normalized_username,
        profile_picture=profile_picture,
    )
    if not user:
        raise HTTPException(status_code=404, detail="Administrator not found.")
    return {"ok": True, "user": user}
