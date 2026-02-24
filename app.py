from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Any, Literal
import re
from pymongo.errors import DuplicateKeyError

from config import FRONTEND_ORIGIN, MONGODB_DB_NAME, MONGODB_URI
from schemas import TurnResponse
from services.asr_service import transcribe_audio_bytes
from services.turn_service import process_turn, to_call_log_view
from storage.mongo_store import MongoStore

app = FastAPI(title="Shifa Voice Agent")
store = MongoStore(MONGODB_URI, MONGODB_DB_NAME)
ADMIN_SIGNUP_CODE = "8754"

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
    department: str | None = None
    specialization: str | None = None
    status: str = "Available"
    availability: list[DoctorAvailabilitySlot] = Field(default_factory=list)


class DoctorUpdateRequest(BaseModel):
    name: str | None = None
    department: str | None = None
    specialization: str | None = None
    status: str | None = None
    availability: list[DoctorAvailabilitySlot] | None = None


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


@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    return store.get_session(session_id)


@app.get("/dashboard/summary")
def dashboard_summary():
    return store.get_dashboard_summary()


@app.get("/doctors")
def doctors():
    return store.get_doctors()


@app.post("/doctors")
def create_doctor(payload: DoctorCreateRequest):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Doctor name is required.")
    return store.create_doctor(payload.model_dump())


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


@app.get("/call-logs")
def call_logs(limit: int = 100):
    logs = store.get_call_logs(limit=limit)
    return [to_call_log_view(log) for log in logs]


@app.get("/system-monitoring")
def system_monitoring():
    return {
        "overall_status": "All Systems Operational" if store.ping() else "Degraded",
        "database_connected": store.ping(),
        "active_calls": store.call_logs.count_documents({"status": "Completed"}),
        "services": [
            {"name": "ASR Service", "status": "Active"},
            {"name": "LLM Service", "status": "Active"},
            {"name": "TTS Service", "status": "Active"},
            {"name": "Database", "status": "Active" if store.ping() else "Down"},
        ],
    }


@app.post("/auth/signup")
def auth_signup(payload: AdminSignupRequest):
    if payload.code != ADMIN_SIGNUP_CODE:
        raise HTTPException(status_code=403, detail="Invalid signup code.")
    if not payload.name.strip() or not payload.username.strip() or not payload.password.strip():
        raise HTTPException(status_code=400, detail="Name, username, and password are required.")
    try:
        user = store.create_admin_user(name=payload.name, username=payload.username, password=payload.password)
        return {"ok": True, "user": user}
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Username already exists.")


@app.post("/auth/login")
def auth_login(payload: AdminLoginRequest):
    if not payload.username.strip() or not payload.password.strip():
        raise HTTPException(status_code=400, detail="Username and password are required.")
    user = store.authenticate_admin(username=payload.username, password=payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return {"ok": True, "user": user}


@app.post("/auth/forgot-password")
def auth_forgot_password(payload: AdminForgotPasswordRequest):
    if payload.code != ADMIN_SIGNUP_CODE:
        raise HTTPException(status_code=403, detail="Invalid reset code.")
    if not payload.username.strip() or not payload.new_password.strip():
        raise HTTPException(status_code=400, detail="Username and new password are required.")
    updated = store.reset_admin_password(username=payload.username, new_password=payload.new_password)
    if not updated:
        raise HTTPException(status_code=404, detail="Username not found.")
    return {"ok": True}
