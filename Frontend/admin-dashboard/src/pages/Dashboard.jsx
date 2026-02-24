import { useEffect, useState } from "react";
import StatCard from "../components/StatCard";
import ListCard from "../components/ListCard";
import Badge from "../components/Badge";
import { api, formatDateTime } from "../api/client";

function statusVariant(status) {
  if (!status) return "gray";
  const value = status.toLowerCase();
  if (value.includes("confirm") || value.includes("complete")) return "green";
  if (value.includes("pending") || value.includes("busy")) return "yellow";
  if (value.includes("cancel") || value.includes("drop")) return "red";
  return "blue";
}

function parseScheduledDate(value) {
  if (!value) return null;
  const raw = String(value).trim();
  const first = raw.split(" ")[0];
  const isoDateOnly = /^\d{4}-\d{2}-\d{2}$/;
  if (isoDateOnly.test(first)) {
    const dt = new Date(`${first}T00:00:00`);
    if (!Number.isNaN(dt.getTime())) return dt;
  }
  const parsed = new Date(raw);
  if (!Number.isNaN(parsed.getTime())) return parsed;
  return null;
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [upcoming, setUpcoming] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([api.getDashboardSummary(), api.getAppointments()])
      .then(([summary, appointments]) => {
        if (!active) return;
        setData(summary);

        const now = new Date();
        const todayKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
        const todayRows = (appointments || [])
          .filter((row) => String(row.status || "").toLowerCase() !== "cancelled")
          .filter((row) => {
            const dt = parseScheduledDate(row.scheduled_for);
            if (!dt) return false;
            const key = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
            return key === todayKey;
          })
          .sort((a, b) => String(a.scheduled_for || "").localeCompare(String(b.scheduled_for || "")))
          .slice(0, 6);
        setUpcoming(todayRows);
      })
      .catch((err) => {
        if (!active) return;
        setError(err.message || "Failed to load dashboard");
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  if (loading) return <div className="card cardPad">Loading dashboard...</div>;
  if (error) return <div className="card cardPad">{error}</div>;

  const stats = [
    {
      title: "Total Appointments",
      value: String(data?.stats?.total_appointments ?? 0),
      subtitle: "From MongoDB",
      icon: "APT",
    },
    {
      title: "Active Doctors",
      value: String(data?.stats?.active_doctors ?? 0),
      subtitle: "Currently available",
      icon: "DR",
    },
    {
      title: "Voice Calls Today",
      value: String(data?.stats?.calls_today ?? 0),
      subtitle: "Handled by AI",
      icon: "CALL",
    },
    {
      title: "System Status",
      value: String(data?.stats?.system_status ?? "Unknown"),
      subtitle: "Backend health",
      icon: "SYS",
    },
  ];

  return (
    <div>
      <div className="h1">Dashboard Overview</div>
      <div className="small">Live data from backend and MongoDB.</div>

      <div className="mt16 grid4">
        {stats.map((s) => (
          <StatCard key={s.title} {...s} />
        ))}
      </div>

      <div className="mt16 grid2">
        <ListCard title="Upcoming Appointments" icon="APT" rightAction={<span className="small">Latest</span>}>
          {upcoming.length === 0 ? (
            <div className="listRow">No appointments yet.</div>
          ) : (
            upcoming.map((u) => (
              <div key={u.id} className="listRow">
                <div>
                  <div className="listMain">{u.patient_name || "Unknown Patient"}</div>
                  <div className="listSub">{u.doctor_name || "Doctor not mapped"}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div className="listMain">{u.scheduled_for || "TBD"}</div>
                  <div className="mt8">
                    <Badge variant={statusVariant(u.status)}>{u.status || "Pending"}</Badge>
                  </div>
                </div>
              </div>
            ))
          )}
        </ListCard>

        <ListCard title="Recent Voice Calls" icon="LOG" rightAction={<span className="small">Latest</span>}>
          {(data?.recent_calls || []).length === 0 ? (
            <div className="listRow">No calls yet.</div>
          ) : (
            (data?.recent_calls || []).map((c) => (
              <div key={c.id} className="listRow">
                <div>
                  <div className="listMain">{c.entities?.patient_name || "Unknown Caller"}</div>
                  <div className="listSub">Intent: {c.intent || "other"}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div className="listMain">{formatDateTime(c.created_at)}</div>
                  <div className="listSub">{(c.confidence || 0).toFixed(2)}</div>
                </div>
              </div>
            ))
          )}
        </ListCard>
      </div>
    </div>
  );
}
