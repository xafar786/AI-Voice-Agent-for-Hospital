import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { clearCurrentUser, getCurrentUser } from "../auth";

function toLower(value) {
  return String(value || "").toLowerCase();
}

export default function Header() {
  const navigate = useNavigate();
  const user = getCurrentUser();
  const name = user?.name || "Admin";
  const username = user?.username || "admin";
  const avatar = (name || "A").trim().slice(0, 1).toUpperCase();

  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);

  const normalizedQuery = useMemo(() => query.trim().toLowerCase(), [query]);

  useEffect(() => {
    let active = true;
    if (normalizedQuery.length < 2) {
      setResults([]);
      setLoading(false);
      return () => {
        active = false;
      };
    }

    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const [patients, doctors, appointments] = await Promise.all([
          api.getPatients(),
          api.getDoctors(),
          api.getAppointments(),
        ]);
        if (!active) return;

        const patientHits = patients
          .filter((p) =>
            [p.patient_id, p.name, p.phone]
              .filter(Boolean)
              .some((v) => toLower(v).includes(normalizedQuery))
          )
          .slice(0, 4)
          .map((p) => ({
            id: `p-${p.id}`,
            type: "Patient",
            title: p.name || "Unknown Patient",
            subtitle: p.patient_id || p.phone || "",
            path: "/patients",
          }));

        const doctorHits = doctors
          .filter((d) =>
            [d.doctor_id, d.name, d.department, d.specialization]
              .filter(Boolean)
              .some((v) => toLower(v).includes(normalizedQuery))
          )
          .slice(0, 4)
          .map((d) => ({
            id: `d-${d.id}`,
            type: "Doctor",
            title: d.name || "Unknown Doctor",
            subtitle: d.doctor_id || d.department || "",
            path: "/doctors",
          }));

        const appointmentHits = appointments
          .filter((a) =>
            [a.appointment_id, a.patient_name, a.doctor_name, a.scheduled_for]
              .filter(Boolean)
              .some((v) => toLower(v).includes(normalizedQuery))
          )
          .slice(0, 6)
          .map((a) => ({
            id: `a-${a.id}`,
            type: "Appointment",
            title: `${a.patient_name || "Unknown"} / ${a.doctor_name || "Unassigned"}`,
            subtitle: `${a.appointment_id || ""} ${a.scheduled_for || ""}`.trim(),
            path: "/appointments",
          }));

        setResults([...patientHits, ...doctorHits, ...appointmentHits]);
      } catch {
        if (!active) return;
        setResults([]);
      } finally {
        if (!active) return;
        setLoading(false);
      }
    }, 300);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [normalizedQuery]);

  function handleLogout() {
    clearCurrentUser();
    navigate("/login", { replace: true });
  }

  function handleSelect(path) {
    setOpen(false);
    navigate(path);
  }

  return (
    <header className="header">
      <div className="headerLeft">
        <div className="title">AI Voice Agent for Hospital</div>
        <div className="sub">Admin Dashboard</div>
      </div>

      <div className="searchWrap">
        <input
          className="search"
          placeholder="Search patients, doctors, appointments..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setOpen(true)}
        />
        {open && query.trim().length > 0 && (
          <div className="searchDropdown">
            {loading && <div className="searchItem searchMeta">Searching...</div>}
            {!loading && results.length === 0 && <div className="searchItem searchMeta">No results</div>}
            {!loading &&
              results.map((item) => (
                <button key={item.id} className="searchItem" type="button" onClick={() => handleSelect(item.path)}>
                  <div className="searchType">{item.type}</div>
                  <div className="searchMain">{item.title}</div>
                  <div className="searchSub">{item.subtitle}</div>
                </button>
              ))}
          </div>
        )}
      </div>

      <div className="row gap12">
        <div className="profile">
          <div className="profileTxt">
            <div className="name">{name}</div>
            <div className="role">@{username}</div>
          </div>
          <div className="avatar">{avatar}</div>
        </div>
        <button className="btn" onClick={handleLogout} type="button">Logout</button>
      </div>
    </header>
  );
}
