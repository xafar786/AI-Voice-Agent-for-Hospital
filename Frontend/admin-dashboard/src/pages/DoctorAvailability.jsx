import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";

const WEEK_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

function makeTimeSlots(startHour = 8, endHour = 20, stepMinutes = 15) {
  const slots = [];
  for (let hour = startHour; hour < endHour; hour += 1) {
    for (let minutes = 0; minutes < 60; minutes += stepMinutes) {
      const h = String(hour).padStart(2, "0");
      const m = String(minutes).padStart(2, "0");
      slots.push(`${h}:${m}`);
    }
  }
  return slots;
}

function toAvailabilityMap(availability) {
  const out = {};
  WEEK_DAYS.forEach((day) => {
    out[day] = new Set();
  });

  (availability || []).forEach((row) => {
    const day = row?.day;
    if (!WEEK_DAYS.includes(day)) return;
    const slots = row?.slots || row?.timeslots || [];
    (slots || []).forEach((slot) => {
      if (typeof slot === "string") out[day].add(slot);
    });
  });
  return out;
}

function cloneMap(mapData) {
  const out = {};
  WEEK_DAYS.forEach((day) => {
    out[day] = new Set(mapData[day] || []);
  });
  return out;
}

function mapsEqual(a, b) {
  return WEEK_DAYS.every((day) => {
    const aa = a[day] || new Set();
    const bb = b[day] || new Set();
    if (aa.size !== bb.size) return false;
    for (const slot of aa) {
      if (!bb.has(slot)) return false;
    }
    return true;
  });
}

function mapToPayload(mapData) {
  return WEEK_DAYS.map((day) => {
    const slots = Array.from(mapData[day] || []).sort();
    return { day, slots };
  }).filter((row) => row.slots.length > 0);
}

export default function DoctorAvailability() {
  const { doctorId } = useParams();
  const navigate = useNavigate();
  const timeSlots = useMemo(() => makeTimeSlots(8, 20, 15), []);

  const [doctor, setDoctor] = useState(null);
  const [initialMap, setInitialMap] = useState(() => toAvailabilityMap([]));
  const [selectedMap, setSelectedMap] = useState(() => toAvailabilityMap([]));
  const [copyFromDay, setCopyFromDay] = useState("Monday");
  const [copyToDay, setCopyToDay] = useState("Tuesday");
  const [isDragging, setIsDragging] = useState(false);
  const [dragValue, setDragValue] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const isDirty = useMemo(() => !mapsEqual(initialMap, selectedMap), [initialMap, selectedMap]);

  useEffect(() => {
    async function loadDoctor() {
      try {
        const doctors = await api.getDoctors();
        const found = doctors.find((d) => d.id === doctorId);
        if (!found) {
          setError("Doctor not found.");
          return;
        }
        const mapData = toAvailabilityMap(found.availability || []);
        setDoctor(found);
        setInitialMap(mapData);
        setSelectedMap(cloneMap(mapData));
      } catch (err) {
        setError(err.message || "Failed to load doctor availability.");
      } finally {
        setLoading(false);
      }
    }
    loadDoctor();
  }, [doctorId]);

  useEffect(() => {
    function onMouseUp() {
      setIsDragging(false);
    }

    function onBeforeUnload(event) {
      if (!isDirty) return;
      event.preventDefault();
      event.returnValue = "";
    }

    window.addEventListener("mouseup", onMouseUp);
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => {
      window.removeEventListener("mouseup", onMouseUp);
      window.removeEventListener("beforeunload", onBeforeUnload);
    };
  }, [isDirty]);

  function applySlot(day, slot, value) {
    setSelectedMap((prev) => {
      const next = cloneMap(prev);
      if (value) next[day].add(slot);
      else next[day].delete(slot);
      return next;
    });
  }

  function onCellMouseDown(day, slot) {
    const alreadySelected = selectedMap[day]?.has(slot);
    const newValue = !alreadySelected;
    setDragValue(newValue);
    setIsDragging(true);
    applySlot(day, slot, newValue);
  }

  function onCellMouseEnter(day, slot) {
    if (!isDragging) return;
    applySlot(day, slot, dragValue);
  }

  function clearDay(day) {
    setSelectedMap((prev) => {
      const next = cloneMap(prev);
      next[day] = new Set();
      return next;
    });
  }

  function copyDaySlots() {
    if (copyFromDay === copyToDay) return;
    setSelectedMap((prev) => {
      const next = cloneMap(prev);
      next[copyToDay] = new Set(next[copyFromDay] || []);
      return next;
    });
  }

  async function saveAvailability() {
    if (!doctor?.id) return;
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const payload = { availability: mapToPayload(selectedMap) };
      await api.updateDoctor(doctor.id, payload);
      const frozen = cloneMap(selectedMap);
      setInitialMap(frozen);
      setSelectedMap(cloneMap(frozen));
      setSuccess("Availability updated successfully.");
    } catch (err) {
      setError(err.message || "Failed to save availability.");
    } finally {
      setSaving(false);
    }
  }

  function handleBack() {
    if (isDirty && !window.confirm("You have unsaved changes. Leave without saving?")) return;
    navigate("/doctors");
  }

  if (loading) return <div className="card cardPad">Loading availability...</div>;
  if (!doctor) return <div className="card cardPad">{error || "Doctor not found."}</div>;

  return (
    <div className="availPage">
      <div className="availHeader">
        <div>
          <div className="h1">Doctor Availability Calendar</div>
          <div className="small">
            {doctor.name} {doctor.department ? `- ${doctor.department}` : ""} {doctor.specialization ? `- ${doctor.specialization}` : ""}
          </div>
        </div>
        <div className="row gap8">
          <button className="btn" onClick={handleBack}>Back to Doctors</button>
          <button className="btn" onClick={handleBack}>Cancel</button>
          <button className="btn btnPrimary" onClick={saveAvailability} disabled={saving}>
            {saving ? "Saving..." : "Save Availability"}
          </button>
        </div>
      </div>

      {error && <div className="card cardPad" style={{ color: "#b91c1c" }}>{error}</div>}
      {success && <div className="card cardPad" style={{ color: "#166534" }}>{success}</div>}

      <div className="card cardPad mt16">
        <div className="row gap8">
          <div className="small" style={{ fontWeight: 800 }}>Copy Day To:</div>
          <select className="input" value={copyFromDay} onChange={(e) => setCopyFromDay(e.target.value)}>
            {WEEK_DAYS.map((day) => <option key={`from-${day}`} value={day}>{day}</option>)}
          </select>
          <span className="small">to</span>
          <select className="input" value={copyToDay} onChange={(e) => setCopyToDay(e.target.value)}>
            {WEEK_DAYS.map((day) => <option key={`to-${day}`} value={day}>{day}</option>)}
          </select>
          <button className="btn" onClick={copyDaySlots}>Copy</button>
        </div>
      </div>

      <div className="card mt16">
        <div className="availGridWrap">
          <div className="availGrid">
            <div className="availHeadRow">
              <div className="availCorner">Time</div>
              {WEEK_DAYS.map((day) => (
                <div key={`head-${day}`} className="availDayHead">
                  <span>{day}</span>
                  <button className="btn btnGhost" onClick={() => clearDay(day)}>Clear Day</button>
                </div>
              ))}
            </div>

            {timeSlots.map((slot) => (
              <div key={`row-${slot}`} className="availRow">
                <div className="availTimeCol">{slot}</div>
                {WEEK_DAYS.map((day) => {
                  const active = selectedMap[day]?.has(slot);
                  return (
                    <button
                      key={`${day}-${slot}`}
                      className={active ? "availCell availCellActive" : "availCell"}
                      onMouseDown={() => onCellMouseDown(day, slot)}
                      onMouseEnter={() => onCellMouseEnter(day, slot)}
                      type="button"
                    />
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
