import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import StatCard from "../components/StatCard";
import Badge from "../components/Badge";
import { api } from "../api/client";

function statusVariant(status) {
  const v = (status || "").toLowerCase();
  if (v.includes("available")) return "green";
  if (v.includes("busy")) return "yellow";
  return "gray";
}

const emptyDoctor = { name: "", department: "", specialization: "", status: "Available", availability: [] };

export default function Doctors() {
  const navigate = useNavigate();
  const [doctors, setDoctors] = useState([]);
  const [search, setSearch] = useState("");
  const [form, setForm] = useState(emptyDoctor);
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [editDoctorId, setEditDoctorId] = useState(null);
  const [editForm, setEditForm] = useState(emptyDoctor);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [error, setError] = useState("");

  async function loadDoctors() {
    const data = await api.getDoctors();
    setDoctors(data);
  }

  useEffect(() => {
    loadDoctors()
      .catch((err) => setError(err.message || "Failed to load doctors"))
      .finally(() => setLoading(false));
  }, []);

  const stats = useMemo(() => {
    const total = doctors.length;
    const available = doctors.filter((d) => (d.status || "").toLowerCase() === "available").length;
    const busy = doctors.filter((d) => (d.status || "").toLowerCase() === "busy").length;
    const onLeave = doctors.filter((d) => (d.status || "").toLowerCase().includes("leave")).length;
    return { total, available, busy, onLeave };
  }, [doctors]);

  const filteredDoctors = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return doctors;
    return doctors.filter((d) =>
      [d.name, d.department, d.specialization, d.status]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(q))
    );
  }, [doctors, search]);

  async function handleCreateDoctor(e) {
    e.preventDefault();
    if (!form.name.trim()) {
      setError("Doctor name is required.");
      return;
    }

    setSaving(true);
    setError("");
    try {
      await api.createDoctor(form);
      setForm(emptyDoctor);
      await loadDoctors();
      setIsAddOpen(false);
    } catch (err) {
      setError(err.message || "Failed to create doctor");
    } finally {
      setSaving(false);
    }
  }

  function openEditDoctor(doc) {
    setEditDoctorId(doc.id);
    setEditForm({
      name: doc.name || "",
      department: doc.department || "",
      specialization: doc.specialization || "",
      status: doc.status || "Available",
      availability: doc.availability || [],
    });
  }

  function closeEditDoctor() {
    setEditDoctorId(null);
    setEditForm(emptyDoctor);
  }

  async function handleUpdateDoctor(e) {
    e.preventDefault();
    if (!editDoctorId) return;
    if (!editForm.name.trim()) {
      setError("Doctor name is required.");
      return;
    }

    setEditSaving(true);
    setError("");
    try {
      await api.updateDoctor(editDoctorId, editForm);
      await loadDoctors();
      closeEditDoctor();
    } catch (err) {
      setError(err.message || "Failed to update doctor");
    } finally {
      setEditSaving(false);
    }
  }

  async function handleDeleteDoctor(doc) {
    if (!window.confirm(`Delete ${doc.name}?`)) return;

    setError("");
    try {
      await api.deleteDoctor(doc.id);
      await loadDoctors();
    } catch (err) {
      setError(err.message || "Failed to delete doctor");
    }
  }

  if (loading) return <div className="card cardPad">Loading doctors...</div>;

  return (
    <div>
      <div className="spread">
        <div>
          <h2>Doctor Management</h2>
          <p className="page-subtitle">Create, update, delete doctors (MongoDB)</p>
        </div>
        <button className="btn btnPrimary" onClick={() => setIsAddOpen(true)}>+ Add Doctor</button>
      </div>

      {error && <div className="card cardPad" style={{ color: "#b91c1c", marginBottom: 14 }}>{error}</div>}

      <div className="grid4">
        <StatCard title="Total Doctors" value={String(stats.total)} icon="DR" />
        <StatCard title="Available Now" value={String(stats.available)} icon="AV" />
        <StatCard title="Busy" value={String(stats.busy)} icon="BZ" />
        <StatCard title="On Leave" value={String(stats.onLeave)} icon="LV" />
      </div>

      <div className="card cardPad mt16">
        <div className="small" style={{ fontWeight: 800, marginBottom: 8 }}>Search Doctor</div>
        <input
          className="input"
          style={{ width: "100%" }}
          placeholder="Search by name, department, specialization, or status..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="card tableCard mt16">
        <table className="table">
          <thead>
            <tr>
              <th>Doctor ID</th>
              <th>Doctor Name</th>
              <th>Department</th>
              <th>Specialization</th>
              <th>Status</th>
              <th>Availability</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredDoctors.map((doc) => (
              <tr key={doc.id}>
                <td>{doc.doctor_id || "-"}</td>
                <td>{doc.name}</td>
                <td>{doc.department || "-"}</td>
                <td>{doc.specialization || "-"}</td>
                <td>
                  <Badge variant={statusVariant(doc.status)}>{doc.status || "Unknown"}</Badge>
                </td>
                <td>{(doc.availability || []).length} day(s)</td>
                <td>
                  <div className="row gap8" style={{ flexWrap: "wrap" }}>
                    <button className="btn btnGhost" onClick={() => openEditDoctor(doc)}>Edit</button>
                    <button className="btn btnGhost" onClick={() => navigate(`/doctors/${doc.id}/availability`)}>Availability</button>
                    <button className="btn" onClick={() => handleDeleteDoctor(doc)}>Delete</button>
                  </div>
                </td>
              </tr>
            ))}
            {filteredDoctors.length === 0 && (
              <tr>
                <td colSpan={7} style={{ textAlign: "center", color: "#6b7280" }}>
                  No doctors found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {isAddOpen && (
        <div className="modalBackdrop" onClick={() => setIsAddOpen(false)}>
          <div className="modalCard" onClick={(e) => e.stopPropagation()}>
            <div className="h2">Add Doctor</div>
            <div className="small mt12">Enter doctor details.</div>

            <form className="mt16" onSubmit={handleCreateDoctor}>
              <div className="modalGrid">
                <label className="small">
                  Doctor Name
                  <input
                    className="input"
                    placeholder="Doctor Name"
                    value={form.name}
                    onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                  />
                </label>
                <label className="small">
                  Department
                  <input
                    className="input"
                    placeholder="Department"
                    value={form.department}
                    onChange={(e) => setForm((p) => ({ ...p, department: e.target.value }))}
                  />
                </label>
                <label className="small">
                  Specialization
                  <input
                    className="input"
                    placeholder="Specialization"
                    value={form.specialization}
                    onChange={(e) => setForm((p) => ({ ...p, specialization: e.target.value }))}
                  />
                </label>
                <label className="small">
                  Status
                  <select
                    className="input"
                    value={form.status}
                    onChange={(e) => setForm((p) => ({ ...p, status: e.target.value }))}
                  >
                    <option>Available</option>
                    <option>Busy</option>
                    <option>On Leave</option>
                  </select>
                </label>
              </div>
              <div className="modalActions mt16">
                <button className="btn" type="button" onClick={() => setIsAddOpen(false)}>Cancel</button>
                <button className="btn btnPrimary" type="submit" disabled={saving}>
                  {saving ? "Saving..." : "Add Doctor"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {editDoctorId && (
        <div className="modalBackdrop" onClick={closeEditDoctor}>
          <div className="modalCard" onClick={(e) => e.stopPropagation()}>
            <div className="h2">Edit Doctor</div>
            <div className="small mt12">Update doctor details below.</div>

            <form className="mt16" onSubmit={handleUpdateDoctor}>
              <div className="modalGrid">
                <label className="small">
                  Doctor Name
                  <input
                    className="input"
                    placeholder="Doctor Name"
                    value={editForm.name}
                    onChange={(e) => setEditForm((p) => ({ ...p, name: e.target.value }))}
                  />
                </label>
                <label className="small">
                  Department
                  <input
                    className="input"
                    placeholder="Department"
                    value={editForm.department}
                    onChange={(e) => setEditForm((p) => ({ ...p, department: e.target.value }))}
                  />
                </label>
                <label className="small">
                  Specialization
                  <input
                    className="input"
                    placeholder="Specialization"
                    value={editForm.specialization}
                    onChange={(e) => setEditForm((p) => ({ ...p, specialization: e.target.value }))}
                  />
                </label>
                <label className="small">
                  Status
                  <select
                    className="input"
                    value={editForm.status}
                    onChange={(e) => setEditForm((p) => ({ ...p, status: e.target.value }))}
                  >
                    <option>Available</option>
                    <option>Busy</option>
                    <option>On Leave</option>
                  </select>
                </label>
              </div>

              <div className="modalActions mt16">
                <button className="btn" type="button" onClick={closeEditDoctor}>Cancel</button>
                <button className="btn btnPrimary" type="submit" disabled={editSaving}>
                  {editSaving ? "Updating..." : "Update"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
