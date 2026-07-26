import { useEffect, useMemo, useRef, useState } from "react";
import Badge from "../components/Badge";
import { api } from "../api/client";

function statusVariant(status) {
  const v = (status || "").toLowerCase();
  if (v.includes("cancel")) return "red";
  if (v.includes("pending") || v.includes("resched")) return "yellow";
  return "green";
}

const emptyNewPatient = {
  name: "",
  phone: "",
  conditions: "",
  status: "Active",
};

function toDateKey(dateObj) {
  return `${dateObj.getFullYear()}-${String(dateObj.getMonth() + 1).padStart(2, "0")}-${String(dateObj.getDate()).padStart(2, "0")}`;
}

function parseAppointmentDate(value) {
  if (!value) return null;
  const text = String(value).trim();
  const first = text.split(" ")[0];
  const fullDate = new Date(text);
  if (!Number.isNaN(fullDate.getTime())) return fullDate;
  const firstDate = new Date(first);
  if (!Number.isNaN(firstDate.getTime())) return firstDate;
  return null;
}

function parseScheduledFor(value) {
  const text = String(value || "").trim();
  const parts = text.split(" ");
  if (parts.length >= 2) {
    return { date: parts[0], slot: parts[1] };
  }
  return { date: "", slot: "" };
}

export default function Appointments() {
  const [appointments, setAppointments] = useState([]);
  const [doctors, setDoctors] = useState([]);
  const [patients, setPatients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [step, setStep] = useState(1);
  const [patientType, setPatientType] = useState("");
  const [newPatient, setNewPatient] = useState(emptyNewPatient);
  const [oldPatientId, setOldPatientId] = useState("");
  const [selectedDoctorId, setSelectedDoctorId] = useState("");
  const [selectedDate, setSelectedDate] = useState("");
  const [selectedSlot, setSelectedSlot] = useState("");
  const [reason, setReason] = useState("");
  const [booking, setBooking] = useState(false);
  const [modalError, setModalError] = useState("");
  const bookingLockRef = useRef(false);
  const [editAppointment, setEditAppointment] = useState(null);
  const [editForm, setEditForm] = useState({
    doctor_id: "",
    appointment_date: "",
    slot: "",
    reason: "",
    status: "Booked",
  });
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState("");
  const [deletingId, setDeletingId] = useState("");
  const [calendarMonth, setCalendarMonth] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });

  async function loadAll() {
    const [appts, docs, pats] = await Promise.all([
      api.getAppointments(),
      api.getDoctors(),
      api.getPatients(),
    ]);
    setAppointments(appts);
    setDoctors(docs);
    setPatients(pats);
  }

  useEffect(() => {
    loadAll()
      .catch((err) => setError(err.message || "Failed to load appointments"))
      .finally(() => setLoading(false));
  }, []);

  const calendarData = useMemo(() => {
    const byDay = new Map();
    appointments.forEach((appt) => {
      const parsed = parseAppointmentDate(appt.scheduled_for);
      if (!parsed) return;
      const key = toDateKey(parsed);
      if (!byDay.has(key)) byDay.set(key, []);
      byDay.get(key).push(appt);
    });

    const year = calendarMonth.getFullYear();
    const month = calendarMonth.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDate = new Date(year, month + 1, 0).getDate();
    const startWeekday = firstDay.getDay();
    const weeks = [];
    let cursor = 1 - startWeekday;
    while (cursor <= lastDate) {
      const week = [];
      for (let i = 0; i < 7; i += 1) {
        const dayDate = new Date(year, month, cursor);
        const inMonth = dayDate.getMonth() === month;
        const key = toDateKey(dayDate);
        week.push({
          key,
          day: dayDate.getDate(),
          inMonth,
          items: inMonth ? byDay.get(key) || [] : [],
        });
        cursor += 1;
      }
      weeks.push(week);
    }
    return weeks;
  }, [appointments, calendarMonth]);

  const selectedDoctor = useMemo(
    () => doctors.find((d) => d.id === selectedDoctorId) || null,
    [doctors, selectedDoctorId]
  );

  const selectedWeekDay = useMemo(() => {
    if (!selectedDate) return "";
    const dateObj = new Date(`${selectedDate}T00:00:00`);
    if (Number.isNaN(dateObj.getTime())) return "";
    return dateObj.toLocaleDateString("en-US", { weekday: "long" });
  }, [selectedDate]);

  const slotOptions = useMemo(() => {
    if (!selectedDoctor || !selectedWeekDay) return [];
    const row = (selectedDoctor.availability || []).find((item) => item.day === selectedWeekDay);
    return row?.slots || [];
  }, [selectedDoctor, selectedWeekDay]);

  const matchedOldPatient = useMemo(() => {
    const id = oldPatientId.trim();
    if (!id) return null;
    return patients.find((p) => p.patient_id === id) || null;
  }, [patients, oldPatientId]);

  const calendarTitle = useMemo(
    () => calendarMonth.toLocaleDateString(undefined, { month: "long", year: "numeric" }),
    [calendarMonth]
  );

  const selectedEditDoctor = useMemo(
    () => doctors.find((d) => d.id === editForm.doctor_id) || null,
    [doctors, editForm.doctor_id]
  );

  const selectedEditWeekDay = useMemo(() => {
    if (!editForm.appointment_date) return "";
    const dateObj = new Date(`${editForm.appointment_date}T00:00:00`);
    if (Number.isNaN(dateObj.getTime())) return "";
    return dateObj.toLocaleDateString("en-US", { weekday: "long" });
  }, [editForm.appointment_date]);

  const editSlotOptions = useMemo(() => {
    if (!selectedEditDoctor || !selectedEditWeekDay) return [];
    const row = (selectedEditDoctor.availability || []).find((item) => item.day === selectedEditWeekDay);
    return row?.slots || [];
  }, [selectedEditDoctor, selectedEditWeekDay]);

  function openModal() {
    setIsModalOpen(true);
    setStep(1);
    setPatientType("");
    setNewPatient(emptyNewPatient);
    setOldPatientId("");
    setSelectedDoctorId("");
    setSelectedDate("");
    setSelectedSlot("");
    setReason("");
    setModalError("");
  }

  function closeModal() {
    setIsModalOpen(false);
    setModalError("");
  }

  function openEditModal(appt) {
    const parsed = parseScheduledFor(appt.scheduled_for);
    setEditAppointment(appt);
    setEditForm({
      doctor_id: appt.doctor_id || "",
      appointment_date: parsed.date || "",
      slot: parsed.slot || "",
      reason: appt.reason || "",
      status: appt.status || "Booked",
    });
    setEditError("");
  }

  function closeEditModal() {
    setEditAppointment(null);
    setEditError("");
  }

  function nextFromStep1() {
    setModalError("");
    if (!patientType) {
      setModalError("Please select patient type.");
      return;
    }
    setStep(2);
  }

  function nextFromStep2() {
    setModalError("");
    if (patientType === "new") {
      if (!newPatient.name.trim()) {
        setModalError("Patient name is required.");
        return;
      }
    } else {
      if (!oldPatientId.trim()) {
        setModalError("Patient ID is required.");
        return;
      }
      if (!matchedOldPatient) {
        setModalError("No patient found for this Patient ID.");
        return;
      }
    }
    setStep(3);
  }

  async function createAppointment() {
    if (bookingLockRef.current) return;
    bookingLockRef.current = true;
    setModalError("");
    if (!selectedDoctorId) {
      setModalError("Please select doctor.");
      bookingLockRef.current = false;
      return;
    }
    if (!selectedDate) {
      setModalError("Please select appointment date.");
      bookingLockRef.current = false;
      return;
    }
    if (!selectedSlot) {
      setModalError("Please select time slot.");
      bookingLockRef.current = false;
      return;
    }

    const payload = {
      patient_type: patientType,
      doctor_id: selectedDoctorId,
      appointment_date: selectedDate,
      day: selectedWeekDay,
      slot: selectedSlot,
      reason: reason || null,
    };
    if (patientType === "new") {
      payload.patient = {
        name: newPatient.name,
        phone: newPatient.phone || null,
        status: newPatient.status,
        conditions: newPatient.conditions
          .split(",")
          .map((c) => c.trim())
          .filter(Boolean),
      };
    } else {
      payload.patient_id = oldPatientId.trim();
    }

    setBooking(true);
    try {
      await api.createManualAppointment(payload);
      closeModal();
      await loadAll();
    } catch (err) {
      setModalError(err.message || "Failed to create appointment");
    } finally {
      setBooking(false);
      bookingLockRef.current = false;
    }
  }

  async function updateAppointment() {
    if (!editAppointment?.id) return;
    if (!editForm.doctor_id || !editForm.appointment_date || !editForm.slot) {
      setEditError("Doctor, appointment date and slot are required.");
      return;
    }
    setEditSaving(true);
    setEditError("");
    try {
      await api.updateAppointment(editAppointment.id, {
        doctor_id: editForm.doctor_id,
        appointment_date: editForm.appointment_date,
        slot: editForm.slot,
        reason: editForm.reason || null,
        status: editForm.status || "Booked",
      });
      closeEditModal();
      await loadAll();
    } catch (err) {
      setEditError(err.message || "Failed to update appointment");
    } finally {
      setEditSaving(false);
    }
  }

  async function cancelAppointment(appt) {
    if (String(appt.status || "").toLowerCase() === "cancelled") return;
    if (!window.confirm(`Cancel appointment ${appt.appointment_id || appt.id}?`)) return;
    try {
      await api.cancelAppointment(appt.id);
      await loadAll();
    } catch (err) {
      setError(err.message || "Failed to cancel appointment");
    }
  }

  async function deleteAppointment(appt) {
    const label = appt.appointment_id || appt.id;
    if (!window.confirm(`Permanently delete appointment ${label}? This cannot be undone.`)) return;
    setDeletingId(appt.id);
    setError("");
    try {
      await api.deleteAppointment(appt.id);
      if (editAppointment?.id === appt.id) closeEditModal();
      await loadAll();
    } catch (err) {
      setError(err.message || "Failed to delete appointment");
    } finally {
      setDeletingId("");
    }
  }

  if (loading) return <div className="card cardPad">Loading appointments...</div>;
  if (error) return <div className="card cardPad">{error}</div>;

  return (
    <div>
      <div className="spread">
        <div>
          <div className="h1">Appointment Management</div>
          <div className="small">Live appointments mapped from intent entities</div>
        </div>
        <button className="btn btnPrimary" onClick={openModal}>New Appointment</button>
      </div>

      <div className="mt16 grid2">
        <div className="card cardPad">
          <div className="spread">
            <div className="h2">Appointments by Date</div>
            <div className="row gap8">
              <button
                className="btn btnGhost"
                type="button"
                onClick={() => setCalendarMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() - 1, 1))}
              >
                Prev
              </button>
              <div className="small" style={{ fontWeight: 800, minWidth: 130, textAlign: "center" }}>{calendarTitle}</div>
              <button
                className="btn btnGhost"
                type="button"
                onClick={() => setCalendarMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() + 1, 1))}
              >
                Next
              </button>
            </div>
          </div>

          <div className="mt12 apptCalendar">
            <div className="apptCalHead">
              {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((label) => (
                <div key={label} className="apptCalHeadCell">{label}</div>
              ))}
            </div>
            <div className="apptCalBody">
              {calendarData.flat().map((cell) => (
                <div key={cell.key} className={cell.inMonth ? "apptCalCell" : "apptCalCell apptCalCellMuted"}>
                  <div className="apptCalDay">{cell.day}</div>
                  {cell.inMonth && cell.items.slice(0, 2).map((item) => (
                    <div key={item.id} className="apptCalItem">
                      {(item.patient_name || "Unknown")} / {(item.doctor_name || "Unassigned")}
                    </div>
                  ))}
                  {cell.inMonth && cell.items.length > 2 && (
                    <div className="small">+{cell.items.length - 2} more</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="card">
          <div className="cardHead spread">
            <div className="cardTitle">Upcoming</div>
          </div>
          <div>
            {appointments.slice(0, 12).map((u) => (
              <div key={u.id} className="listRow">
                <div>
                  <div className="listMain">{u.patient_name || "Unknown Patient"}</div>
                  <div className="listSub">{u.doctor_name || "Doctor not mapped"}</div>
                  <div className="listSub">{u.scheduled_for || "TBD"}</div>
                  <div className="listSub">ID: {u.appointment_id || "-"}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <Badge variant={statusVariant(u.status)}>{u.status || "Pending"}</Badge>
                  <div className="row gap8" style={{ marginTop: 8, justifyContent: "flex-end" }}>
                    <button className="btn btnGhost" type="button" onClick={() => openEditModal(u)}>Edit</button>
                    <button className="btn" type="button" onClick={() => cancelAppointment(u)} disabled={String(u.status || "").toLowerCase() === "cancelled"}>
                      Cancel
                    </button>
                    <button
                      className="btn"
                      type="button"
                      onClick={() => deleteAppointment(u)}
                      disabled={deletingId === u.id}
                    >
                      {deletingId === u.id ? "Deleting..." : "Delete"}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {isModalOpen && (
        <div className="modalBackdrop" onClick={closeModal}>
          <div className="modalCard" onClick={(e) => e.stopPropagation()}>
            <div className="h2">New Appointment</div>
            <div className="small mt12">Step {step} of 3</div>
            {modalError && <div className="authMsg authErr mt12">{modalError}</div>}

            {step === 1 && (
              <div className="mt16 apptWizardCol">
                <div className="small" style={{ fontWeight: 800 }}>Select Patient Type</div>
                <label className="apptOption">
                  <input
                    type="radio"
                    name="patientType"
                    checked={patientType === "new"}
                    onChange={() => setPatientType("new")}
                  />
                  <span>1. New Patient</span>
                </label>
                <label className="apptOption">
                  <input
                    type="radio"
                    name="patientType"
                    checked={patientType === "old"}
                    onChange={() => setPatientType("old")}
                  />
                  <span>2. Old Patient</span>
                </label>
                <div className="modalActions mt16">
                  <button className="btn" onClick={closeModal} type="button">Cancel</button>
                  <button className="btn btnPrimary" onClick={nextFromStep1} type="button">Next</button>
                </div>
              </div>
            )}

            {step === 2 && patientType === "new" && (
              <div className="mt16">
                <div className="modalGrid">
                  <label className="small">
                    Patient Name
                    <input className="input" value={newPatient.name} onChange={(e) => setNewPatient((p) => ({ ...p, name: e.target.value }))} />
                  </label>
                  <label className="small">
                    Phone
                    <input className="input" value={newPatient.phone} onChange={(e) => setNewPatient((p) => ({ ...p, phone: e.target.value }))} />
                  </label>
                  <label className="small">
                    Status
                    <select className="input" value={newPatient.status} onChange={(e) => setNewPatient((p) => ({ ...p, status: e.target.value }))}>
                      <option>Active</option>
                      <option>Inactive</option>
                      <option>Critical</option>
                    </select>
                  </label>
                  <label className="small">
                    Conditions (comma separated)
                    <input className="input" value={newPatient.conditions} onChange={(e) => setNewPatient((p) => ({ ...p, conditions: e.target.value }))} />
                  </label>
                </div>
                <div className="modalActions mt16">
                  <button className="btn" onClick={() => setStep(1)} type="button">Back</button>
                  <button className="btn btnPrimary" onClick={nextFromStep2} type="button">Next</button>
                </div>
              </div>
            )}

            {step === 2 && patientType === "old" && (
              <div className="mt16 apptWizardCol">
                <label className="small">
                  Enter Patient ID
                  <input className="input" value={oldPatientId} onChange={(e) => setOldPatientId(e.target.value)} placeholder="PC1" />
                </label>
                {matchedOldPatient && (
                  <div className="small">
                    Found: {matchedOldPatient.name} ({matchedOldPatient.patient_id})
                  </div>
                )}
                <div className="modalActions mt16">
                  <button className="btn" onClick={() => setStep(1)} type="button">Back</button>
                  <button className="btn btnPrimary" onClick={nextFromStep2} type="button">Next</button>
                </div>
              </div>
            )}

            {step === 3 && (
              <div className="mt16 apptWizardCol">
                <label className="small">
                  Select Doctor
                  <select
                    className="input"
                    value={selectedDoctorId}
                    onChange={(e) => {
                      setSelectedDoctorId(e.target.value);
                      setSelectedDate("");
                      setSelectedSlot("");
                    }}
                  >
                    <option value="">Select doctor</option>
                    {doctors.map((doc) => (
                      <option key={doc.id} value={doc.id}>
                        {doc.name} ({doc.doctor_id})
                      </option>
                    ))}
                  </select>
                </label>

                <label className="small">
                  Appointment Date
                  <input
                    className="input"
                    type="date"
                    value={selectedDate}
                    onChange={(e) => {
                      setSelectedDate(e.target.value);
                      setSelectedSlot("");
                    }}
                    disabled={!selectedDoctorId}
                  />
                </label>

                {selectedDate && selectedWeekDay && (
                  <div className="small">Selected Day: {selectedWeekDay}</div>
                )}

                <label className="small">
                  Available Time Slots
                  <select
                    className="input"
                    value={selectedSlot}
                    onChange={(e) => setSelectedSlot(e.target.value)}
                    disabled={!selectedDate}
                  >
                    <option value="">Select slot</option>
                    {slotOptions.map((slot) => (
                      <option key={slot} value={slot}>{slot}</option>
                    ))}
                  </select>
                </label>
                {selectedDate && selectedWeekDay && slotOptions.length === 0 && (
                  <div className="small" style={{ color: "#b45309" }}>
                    No available slots for {selectedWeekDay}.
                  </div>
                )}

                <label className="small">
                  Reason (optional)
                  <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} />
                </label>

                <div className="modalActions mt16">
                  <button className="btn" onClick={() => setStep(2)} type="button">Back</button>
                  <button className="btn btnPrimary" onClick={createAppointment} type="button" disabled={booking}>
                    {booking ? "Booking..." : "Book Appointment"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {editAppointment && (
        <div className="modalBackdrop" onClick={closeEditModal}>
          <div className="modalCard" onClick={(e) => e.stopPropagation()}>
            <div className="h2">Update Appointment</div>
            <div className="small mt12">Appointment: {editAppointment.appointment_id || editAppointment.id}</div>
            <div className="small">Patient: {editAppointment.patient_name || editAppointment.patient_id || "-"}</div>
            {editError && <div className="authMsg authErr mt12">{editError}</div>}

            <div className="mt16 apptWizardCol">
              <label className="small">
                Doctor
                <select
                  className="input"
                  value={editForm.doctor_id}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, doctor_id: e.target.value, slot: "" }))}
                >
                  <option value="">Select doctor</option>
                  {doctors.map((doc) => (
                    <option key={doc.id} value={doc.id}>
                      {doc.name} ({doc.doctor_id})
                    </option>
                  ))}
                </select>
              </label>

              <label className="small">
                Appointment Date
                <input
                  className="input"
                  type="date"
                  value={editForm.appointment_date}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, appointment_date: e.target.value, slot: "" }))}
                />
              </label>

              {editForm.appointment_date && selectedEditWeekDay && (
                <div className="small">Selected Day: {selectedEditWeekDay}</div>
              )}

              <label className="small">
                Time Slot
                <select
                  className="input"
                  value={editForm.slot}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, slot: e.target.value }))}
                >
                  <option value="">Select slot</option>
                  {editSlotOptions.map((slot) => (
                    <option key={slot} value={slot}>{slot}</option>
                  ))}
                </select>
              </label>

              <label className="small">
                Status
                <select
                  className="input"
                  value={editForm.status}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, status: e.target.value }))}
                >
                  <option>Booked</option>
                  <option>Pending</option>
                  <option>Rescheduled</option>
                  <option>Completed</option>
                  <option>Cancelled</option>
                </select>
              </label>

              <label className="small">
                Reason
                <input
                  className="input"
                  value={editForm.reason}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, reason: e.target.value }))}
                />
              </label>

              <div className="modalActions mt16">
                <button className="btn" type="button" onClick={closeEditModal}>Close</button>
                <button className="btn btnPrimary" type="button" onClick={updateAppointment} disabled={editSaving}>
                  {editSaving ? "Updating..." : "Update Appointment"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
