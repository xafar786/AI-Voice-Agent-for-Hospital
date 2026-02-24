import { useEffect, useMemo, useState } from "react";
import Badge from "../components/Badge";
import { api, formatDateTime } from "../api/client";

function statusVariant(status) {
  const v = (status || "").toLowerCase();
  if (v.includes("active")) return "green";
  if (v.includes("critical")) return "red";
  return "gray";
}

function initialsOf(name) {
  if (!name) return "NA";
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase() || "").join("") || "NA";
}

function Tag({ children }) {
  return <span className="pTag">{children}</span>;
}

const emptyPatient = { name: "", phone: "", conditions: "", status: "Active" };

export default function Patients() {
  const [patients, setPatients] = useState([]);
  const [form, setForm] = useState(emptyPatient);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [editingPatient, setEditingPatient] = useState(null);
  const [editForm, setEditForm] = useState(emptyPatient);
  const [editSaving, setEditSaving] = useState(false);

  const [historyPatient, setHistoryPatient] = useState(null);
  const [historyRows, setHistoryRows] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");

  async function loadPatients() {
    const data = await api.getPatients();
    setPatients(data);
  }

  useEffect(() => {
    loadPatients()
      .catch((err) => setError(err.message || "Failed to load patients"))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    if (!search.trim()) return patients;
    const q = search.toLowerCase();
    return patients.filter((p) =>
      [p.patient_id, p.name, p.phone, ...(p.conditions || [])].filter(Boolean).some((v) => String(v).toLowerCase().includes(q))
    );
  }, [patients, search]);

  async function handleCreatePatient(e) {
    e.preventDefault();
    if (!form.name.trim()) {
      setError("Patient name is required.");
      return;
    }

    setSaving(true);
    setError("");
    try {
      const payload = {
        name: form.name,
        phone: form.phone || null,
        status: form.status,
        conditions: form.conditions
          .split(",")
          .map((c) => c.trim())
          .filter(Boolean),
      };
      await api.createPatient(payload);
      setForm(emptyPatient);
      await loadPatients();
    } catch (err) {
      setError(err.message || "Failed to create patient");
    } finally {
      setSaving(false);
    }
  }

  function openEditModal(patient) {
    setEditingPatient(patient);
    setEditForm({
      name: patient.name || "",
      phone: patient.phone || "",
      status: patient.status || "Active",
      conditions: (patient.conditions || []).join(", "),
    });
  }

  function closeEditModal() {
    setEditingPatient(null);
    setEditForm(emptyPatient);
  }

  async function handleUpdatePatient(e) {
    e.preventDefault();
    if (!editingPatient?.id) return;
    if (!editForm.name.trim()) {
      setError("Patient name is required.");
      return;
    }

    setEditSaving(true);
    setError("");
    try {
      await api.updatePatient(editingPatient.id, {
        name: editForm.name,
        phone: editForm.phone,
        status: editForm.status,
        conditions: editForm.conditions
          .split(",")
          .map((c) => c.trim())
          .filter(Boolean),
      });
      closeEditModal();
      await loadPatients();
    } catch (err) {
      setError(err.message || "Failed to update patient");
    } finally {
      setEditSaving(false);
    }
  }

  async function handleDeletePatient(patient) {
    if (!window.confirm(`Delete ${patient.name}?`)) return;

    setError("");
    try {
      await api.deletePatient(patient.id);
      await loadPatients();
    } catch (err) {
      setError(err.message || "Failed to delete patient");
    }
  }

  async function openHistoryModal(patient) {
    setHistoryPatient(patient);
    setHistoryRows([]);
    setHistoryError("");
    setHistoryLoading(true);
    try {
      const rows = await api.getPatientAppointments(patient.id);
      setHistoryRows(rows);
    } catch (err) {
      setHistoryError(err.message || "Failed to load appointment history");
    } finally {
      setHistoryLoading(false);
    }
  }

  function closeHistoryModal() {
    setHistoryPatient(null);
    setHistoryRows([]);
    setHistoryError("");
    setHistoryLoading(false);
  }

  if (loading) return <div className="card cardPad">Loading patients...</div>;

  return (
    <div>
      <div className="spread">
        <div>
          <div className="h1">Patient Records</div>
          <div className="small">Create, update, delete patients (MongoDB)</div>
        </div>
      </div>

      {error && <div className="card cardPad mt16" style={{ color: "#b91c1c" }}>{error}</div>}

      <div className="mt16 card cardPad">
        <form className="toolbar" onSubmit={handleCreatePatient}>
          <input className="input" placeholder="Patient Name" value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} />
          <input className="input" placeholder="Phone" value={form.phone} onChange={(e) => setForm((p) => ({ ...p, phone: e.target.value }))} />
          <input className="input" placeholder="Conditions (comma separated)" value={form.conditions} onChange={(e) => setForm((p) => ({ ...p, conditions: e.target.value }))} />
          <select className="input" value={form.status} onChange={(e) => setForm((p) => ({ ...p, status: e.target.value }))}>
            <option>Active</option>
            <option>Inactive</option>
            <option>Critical</option>
          </select>
          <button className="btn btnPrimary" type="submit" disabled={saving}>{saving ? "Saving..." : "Add Patient"}</button>
        </form>
      </div>

      <div className="mt16 patientTop">
        <input
          className="input patientSearch"
          placeholder="Search by ID, name, phone, or condition..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />

        <div className="patientStat card cardPad">
          <div className="small" style={{ fontWeight: 800 }}>Total Patients</div>
          <div className="statValue" style={{ fontSize: 18 }}>{patients.length}</div>
        </div>

        <div className="patientStat card cardPad">
          <div className="small" style={{ fontWeight: 800 }}>Matching</div>
          <div className="statValue" style={{ fontSize: 18 }}>{filtered.length}</div>
        </div>
      </div>

      <div className="mt16 patientGrid">
        {filtered.map((p) => (
          <div key={p.id} className="card patientCard">
            <div className="patientCardHead">
              <div className="leftInfo">
                <div className="circle">{initialsOf(p.name)}</div>
                <div>
                  <div className="listMain">{p.name || "Unknown"}</div>
                  <div className="listSub">{p.phone || "No phone"}</div>
                  <div className="listSub">Patient ID: {p.patient_id || "-"}</div>
                </div>
              </div>

              <Badge variant={statusVariant(p.status)}>{p.status || "Inactive"}</Badge>
            </div>

            <div className="patientMeta">
              <div className="listSub">Updated: {formatDateTime(p.updated_at)}</div>
            </div>

            <div className="patientTagRow">
              {(p.conditions || []).length === 0 ? <Tag>No condition</Tag> : (p.conditions || []).map((c) => <Tag key={c}>{c}</Tag>)}
            </div>

            <div className="patientActions patientActions3">
              <button className="btn btnGhost" onClick={() => openHistoryModal(p)}>History</button>
              <button className="btn btnGhost" onClick={() => openEditModal(p)}>Edit</button>
              <button className="btn" onClick={() => handleDeletePatient(p)}>Delete</button>
            </div>
          </div>
        ))}
      </div>

      {editingPatient && (
        <div className="modalBackdrop" onClick={closeEditModal}>
          <div className="modalCard" onClick={(e) => e.stopPropagation()}>
            <div className="h2">Edit Patient</div>
            <div className="small mt12">Patient ID: {editingPatient.patient_id}</div>

            <form className="mt16" onSubmit={handleUpdatePatient}>
              <div className="modalGrid">
                <label className="small">
                  Patient Name
                  <input
                    className="input"
                    value={editForm.name}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, name: e.target.value }))}
                  />
                </label>
                <label className="small">
                  Phone
                  <input
                    className="input"
                    value={editForm.phone}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, phone: e.target.value }))}
                  />
                </label>
                <label className="small">
                  Status
                  <select
                    className="input"
                    value={editForm.status}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, status: e.target.value }))}
                  >
                    <option>Active</option>
                    <option>Inactive</option>
                    <option>Critical</option>
                  </select>
                </label>
                <label className="small">
                  Conditions (comma separated)
                  <input
                    className="input"
                    value={editForm.conditions}
                    onChange={(e) => setEditForm((prev) => ({ ...prev, conditions: e.target.value }))}
                  />
                </label>
              </div>
              <div className="modalActions mt16">
                <button className="btn" type="button" onClick={closeEditModal}>Cancel</button>
                <button className="btn btnPrimary" type="submit" disabled={editSaving}>
                  {editSaving ? "Updating..." : "Update"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {historyPatient && (
        <div className="modalBackdrop" onClick={closeHistoryModal}>
          <div className="modalCard modalWide" onClick={(e) => e.stopPropagation()}>
            <div className="h2">Patient Appointment History</div>
            <div className="small mt12">
              {historyPatient.name} ({historyPatient.patient_id})
            </div>

            {historyLoading && <div className="mt16 small">Loading history...</div>}
            {historyError && <div className="mt16 small" style={{ color: "#b91c1c" }}>{historyError}</div>}

            {!historyLoading && !historyError && (
              <div className="mt16">
                {historyRows.length === 0 ? (
                  <div className="small">No appointments found for this patient.</div>
                ) : (
                  <div className="historyTableWrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Appointment ID</th>
                          <th>Doctor</th>
                          <th>Scheduled For</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {historyRows.map((row) => (
                          <tr key={row.id}>
                            <td>{row.appointment_id || "-"}</td>
                            <td>{row.doctor_name || row.doctor_id || "-"}</td>
                            <td>{row.scheduled_for || "-"}</td>
                            <td><Badge variant={statusVariant(row.status)}>{row.status || "-"}</Badge></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            <div className="modalActions mt16">
              <button className="btn" type="button" onClick={closeHistoryModal}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
