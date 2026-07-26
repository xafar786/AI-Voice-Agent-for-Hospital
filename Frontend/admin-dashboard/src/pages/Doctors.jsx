import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import StatCard from "../components/StatCard";
import Badge from "../components/Badge";
import { api } from "../api/client";
import {
  CalendarOff,
  CircleCheck,
  Clock3,
  Stethoscope,
} from "lucide-react";

function statusVariant(status) {
  const v = (status || "").toLowerCase();
  if (v.includes("available")) return "green";
  if (v.includes("busy")) return "yellow";
  return "gray";
}

const emptyDoctor = {
  name: "",
  urdu_name: "",
  department: "",
  specialization: "",
  qualification: "",
  status: "Available",
  availability: [],
};

const DOCTORS_PER_PAGE = 25;

function doctorIdNumber(doctor) {
  const match = String(doctor.doctor_id || "").match(/(\d+)$/);
  return match ? Number(match[1]) : Number.MAX_SAFE_INTEGER;
}

export default function Doctors() {
  const navigate = useNavigate();
  const [doctors, setDoctors] = useState([]);
  const [search, setSearch] = useState("");
  const [specializationFilter, setSpecializationFilter] = useState("");
  const [availabilityFilter, setAvailabilityFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [sortMode, setSortMode] = useState("id-asc");
  const [form, setForm] = useState(emptyDoctor);
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [isImportOpen, setIsImportOpen] = useState(false);
  const [editDoctorId, setEditDoctorId] = useState(null);
  const [editForm, setEditForm] = useState(emptyDoctor);
  const [importFile, setImportFile] = useState(null);
  const [importResult, setImportResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [error, setError] = useState("");
  const [currentPage, setCurrentPage] = useState(1);

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

  const specializationOptions = useMemo(
    () =>
      [
        ...new Set(
          doctors
            .map((doctor) => String(doctor.specialization || "").trim())
            .filter(Boolean)
        ),
      ]
        .sort((a, b) => a.localeCompare(b)),
    [doctors]
  );

  const statusOptions = useMemo(
    () =>
      [
        ...new Set(
          doctors
            .map((doctor) => String(doctor.status || "").trim())
            .filter(Boolean)
        ),
      ]
        .sort((a, b) => a.localeCompare(b)),
    [doctors]
  );

  const filteredDoctors = useMemo(() => {
    const q = search.trim().toLowerCase();
    return doctors.filter((doctor) => {
      const matchesSearch =
        !q ||
        [
          doctor.name,
          doctor.urdu_name,
          doctor.department,
          doctor.specialization,
          doctor.qualification,
          doctor.status,
        ]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(q));
      const matchesSpecialization =
        !specializationFilter ||
        String(doctor.specialization || "") === specializationFilter;
      const hasAvailability = (doctor.availability || []).some(
        (day) => (day.slots || day.timeslots || []).length > 0
      );
      const matchesAvailability =
        !availabilityFilter ||
        (availabilityFilter === "configured" && hasAvailability) ||
        (availabilityFilter === "not-configured" && !hasAvailability);
      const matchesStatus =
        !statusFilter || String(doctor.status || "") === statusFilter;

      return (
        matchesSearch &&
        matchesSpecialization &&
        matchesAvailability &&
        matchesStatus
      );
    });
  }, [
    availabilityFilter,
    doctors,
    search,
    specializationFilter,
    statusFilter,
  ]);

  const sortedDoctors = useMemo(() => {
    const sorted = [...filteredDoctors];
    sorted.sort((a, b) => {
      if (sortMode === "name-asc" || sortMode === "name-desc") {
        const comparison = String(a.name || "").localeCompare(
          String(b.name || ""),
          undefined,
          { sensitivity: "base", numeric: true }
        );
        return sortMode === "name-desc" ? -comparison : comparison;
      }

      const comparison =
        doctorIdNumber(a) - doctorIdNumber(b) ||
        String(a.doctor_id || "").localeCompare(String(b.doctor_id || ""), undefined, {
          numeric: true,
        });
      return sortMode === "id-desc" ? -comparison : comparison;
    });
    return sorted;
  }, [filteredDoctors, sortMode]);

  const totalPages = Math.max(
    1,
    Math.ceil(sortedDoctors.length / DOCTORS_PER_PAGE)
  );
  const pageStart = (currentPage - 1) * DOCTORS_PER_PAGE;
  const paginatedDoctors = sortedDoctors.slice(
    pageStart,
    pageStart + DOCTORS_PER_PAGE
  );

  useEffect(() => {
    setCurrentPage((page) => Math.min(page, totalPages));
  }, [totalPages]);

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

  async function handleImportDoctors(e) {
    e.preventDefault();
    if (!importFile) {
      setError("Please select a CSV file.");
      return;
    }

    setImporting(true);
    setError("");
    setImportResult(null);
    try {
      const result = await api.importDoctorsCsv(importFile);
      setImportResult(result);
      setImportFile(null);
      await loadDoctors();
    } catch (err) {
      setError(err.message || "Failed to import doctors");
    } finally {
      setImporting(false);
    }
  }

  function closeImportDoctors() {
    setIsImportOpen(false);
    setImportFile(null);
    setImportResult(null);
  }

  function openEditDoctor(doc) {
    setEditDoctorId(doc.id);
    setEditForm({
      name: doc.name || "",
      urdu_name: doc.urdu_name || "",
      department: doc.department || "",
      specialization: doc.specialization || "",
      qualification: doc.qualification || "",
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
        <div className="row gap8" style={{ flexWrap: "wrap" }}>
          <button className="btn" onClick={() => setIsImportOpen(true)}>Import CSV</button>
          <button className="btn btnPrimary" onClick={() => setIsAddOpen(true)}>+ Add Doctor</button>
        </div>
      </div>

      {error && <div className="card cardPad" style={{ color: "#b91c1c", marginBottom: 14 }}>{error}</div>}

      <div className="grid4">
        <StatCard
          title="Total Doctors"
          value={String(stats.total)}
          icon={<Stethoscope size={19} strokeWidth={2.3} aria-hidden="true" />}
        />
        <StatCard
          title="Available Now"
          value={String(stats.available)}
          icon={<CircleCheck size={19} strokeWidth={2.3} aria-hidden="true" />}
        />
        <StatCard
          title="Busy"
          value={String(stats.busy)}
          icon={<Clock3 size={19} strokeWidth={2.3} aria-hidden="true" />}
        />
        <StatCard
          title="On Leave"
          value={String(stats.onLeave)}
          icon={<CalendarOff size={19} strokeWidth={2.3} aria-hidden="true" />}
        />
      </div>

      <div className="card cardPad mt16">
        <div className="doctorFilters">
          <label className="doctorFilterSearch small">
            <span>Search Doctor</span>
            <input
              className="input"
              placeholder="Search by name, department, qualification, or status..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setCurrentPage(1);
              }}
            />
          </label>
          <label className="small">
            <span>Specialization</span>
            <select
              className="input"
              value={specializationFilter}
              onChange={(e) => {
                setSpecializationFilter(e.target.value);
                setCurrentPage(1);
              }}
            >
              <option value="">All specializations</option>
              {specializationOptions.map((specialization) => (
                <option key={specialization} value={specialization}>
                  {specialization}
                </option>
              ))}
            </select>
          </label>
          <label className="small">
            <span>Availability</span>
            <select
              className="input"
              value={availabilityFilter}
              onChange={(e) => {
                setAvailabilityFilter(e.target.value);
                setCurrentPage(1);
              }}
            >
              <option value="">All schedules</option>
              <option value="configured">Has available slots</option>
              <option value="not-configured">No available slots</option>
            </select>
          </label>
          <label className="small">
            <span>Status</span>
            <select
              className="input"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setCurrentPage(1);
              }}
            >
              <option value="">All statuses</option>
              {statusOptions.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
          </label>
          <label className="small">
            <span>Sort Doctors</span>
            <select
              className="input"
              value={sortMode}
              onChange={(e) => {
                setSortMode(e.target.value);
                setCurrentPage(1);
              }}
            >
              <option value="id-asc">ID: Lowest first</option>
              <option value="id-desc">ID: Highest first</option>
              <option value="name-asc">Name: A to Z</option>
              <option value="name-desc">Name: Z to A</option>
            </select>
          </label>
          {(search ||
            specializationFilter ||
            availabilityFilter ||
            statusFilter) && (
            <button
              className="btn doctorClearFilters"
              type="button"
              onClick={() => {
                setSearch("");
                setSpecializationFilter("");
                setAvailabilityFilter("");
                setStatusFilter("");
                setCurrentPage(1);
              }}
            >
              Clear filters
            </button>
          )}
        </div>
      </div>

      <div className="card tableCard mt16">
        <table className="table">
          <thead>
            <tr>
              <th>Doctor ID</th>
              <th>Doctor Name</th>
              <th>Urdu Name</th>
              <th>Department</th>
              <th>Specialization</th>
              <th>Qualification</th>
              <th>Status</th>
              <th>Availability</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {paginatedDoctors.map((doc) => (
              <tr key={doc.id}>
                <td>{doc.doctor_id || "-"}</td>
                <td>{doc.name}</td>
                <td dir="rtl">{doc.urdu_name || "-"}</td>
                <td>{doc.department || "-"}</td>
                <td>{doc.specialization || "-"}</td>
                <td>{doc.qualification || "-"}</td>
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
                <td colSpan={9} style={{ textAlign: "center", color: "#6b7280" }}>
                  No doctors found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {filteredDoctors.length > 0 && (
          <div className="doctorPagination">
            <div className="small">
              Showing {pageStart + 1}–
              {Math.min(pageStart + DOCTORS_PER_PAGE, filteredDoctors.length)} of{" "}
              {filteredDoctors.length} doctors
            </div>
            <div className="doctorPaginationControls">
              <button
                className="btn btnGhost"
                type="button"
                disabled={currentPage === 1}
                onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
              >
                Previous
              </button>
              <span className="doctorPageIndicator">
                Page {currentPage} of {totalPages}
              </span>
              <button
                className="btn btnGhost"
                type="button"
                disabled={currentPage === totalPages}
                onClick={() =>
                  setCurrentPage((page) => Math.min(totalPages, page + 1))
                }
              >
                Next
              </button>
            </div>
          </div>
        )}
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
                  Urdu Name / Spoken Alias
                  <input
                    className="input"
                    dir="rtl"
                    placeholder="ڈاکٹر فہد"
                    value={form.urdu_name}
                    onChange={(e) => setForm((p) => ({ ...p, urdu_name: e.target.value }))}
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
                  Qualification
                  <input
                    className="input"
                    placeholder="Qualification"
                    value={form.qualification}
                    onChange={(e) => setForm((p) => ({ ...p, qualification: e.target.value }))}
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

      {isImportOpen && (
        <div className="modalBackdrop" onClick={closeImportDoctors}>
          <div className="modalCard" onClick={(e) => e.stopPropagation()}>
            <div className="h2">Bulk Import Doctors</div>
            <div className="small mt12">
              Upload a CSV with columns: name, urdu_name, department, specialization, qualification, status.
            </div>

            <form className="mt16" onSubmit={handleImportDoctors}>
              <label className="small">
                CSV File
                <input
                  className="input"
                  type="file"
                  accept=".csv,text/csv"
                  onChange={(e) => {
                    setImportFile(e.target.files?.[0] || null);
                    setImportResult(null);
                  }}
                />
              </label>

              <div className="card cardPad mt16">
                <div className="small" style={{ fontWeight: 800 }}>Sample CSV</div>
                <pre className="small" style={{ margin: "8px 0 0", whiteSpace: "pre-wrap" }}>
{`name,urdu_name,department,specialization,qualification,status
Dr. Ayesha,ڈاکٹر عائشہ,Cardiology,Heart Specialist,MBBS FCPS,Available
Dr. Hamza,ڈاکٹر حمزہ,Dermatology,Skin Specialist,MBBS MCPS,Busy`}
                </pre>
              </div>

              {importResult && (
                <div className="card cardPad mt16">
                  <div className="small" style={{ fontWeight: 800 }}>
                    Imported {importResult.imported_count || 0} doctor(s)
                    {importResult.failed_count ? `, ${importResult.failed_count} row(s) skipped` : ""}
                  </div>
                  {(importResult.errors || []).map((item) => (
                    <div key={`${item.row}-${item.error}`} className="small" style={{ color: "#b91c1c", marginTop: 6 }}>
                      Row {item.row}: {item.error}
                    </div>
                  ))}
                </div>
              )}

              <div className="modalActions mt16">
                <button className="btn" type="button" onClick={closeImportDoctors}>Close</button>
                <button className="btn btnPrimary" type="submit" disabled={importing}>
                  {importing ? "Importing..." : "Import Doctors"}
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
                  Urdu Name / Spoken Alias
                  <input
                    className="input"
                    dir="rtl"
                    placeholder="ڈاکٹر فہد"
                    value={editForm.urdu_name}
                    onChange={(e) => setEditForm((p) => ({ ...p, urdu_name: e.target.value }))}
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
                  Qualification
                  <input
                    className="input"
                    placeholder="Qualification"
                    value={editForm.qualification}
                    onChange={(e) => setEditForm((p) => ({ ...p, qualification: e.target.value }))}
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
