import { useEffect, useState } from "react";
import StatCard from "../components/StatCard";
import ListCard from "../components/ListCard";
import Badge from "../components/Badge";
import {
  api,
  formatDateTime,
  formatPakistanTime,
  getPakistanDateKey,
} from "../api/client";
import {
  CalendarCheck2,
  CalendarDays,
  Headphones,
  PhoneCall,
  ShieldCheck,
  Stethoscope,
} from "lucide-react";

const DASHBOARD_REFRESH_MS = 10_000;

function statusVariant(status) {
  if (!status) return "gray";
  const value = status.toLowerCase();
  if (value.includes("confirm") || value.includes("complete")) return "green";
  if (value.includes("pending") || value.includes("busy")) return "yellow";
  if (value.includes("cancel") || value.includes("drop")) return "red";
  return "blue";
}

function scheduledDateKey(value) {
  if (!value) return "";
  const raw = String(value).trim();
  const first = raw.split(" ")[0];
  if (/^\d{4}-\d{2}-\d{2}$/.test(first)) return first;
  return getPakistanDateKey(raw);
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [upcoming, setUpcoming] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    let requestInFlight = false;

    const refreshDashboard = async (initialLoad = false) => {
      if (requestInFlight) return;
      requestInFlight = true;
      if (!initialLoad) setRefreshing(true);

      try {
        const [summary, appointments] = await Promise.all([
          api.getDashboardSummary(),
          api.getAppointments(),
        ]);
        if (!active) return;
        setData(summary);

        const todayKey = getPakistanDateKey();
        const todayRows = (appointments || [])
          .filter((row) => String(row.status || "").toLowerCase() !== "cancelled")
          .filter((row) => scheduledDateKey(row.scheduled_for) === todayKey)
          .sort((a, b) => String(a.scheduled_for || "").localeCompare(String(b.scheduled_for || "")))
          .slice(0, 6);
        setUpcoming(todayRows);
        setLastUpdated(new Date());
        setError("");
      } catch (err) {
        if (!active) return;
        setError(err.message || "Failed to load dashboard");
      } finally {
        requestInFlight = false;
        if (active) {
          if (initialLoad) setLoading(false);
          setRefreshing(false);
        }
      }
    };

    refreshDashboard(true);
    const refreshTimer = window.setInterval(refreshDashboard, DASHBOARD_REFRESH_MS);
    const refreshOnFocus = () => refreshDashboard();
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") refreshDashboard();
    };
    window.addEventListener("focus", refreshOnFocus);
    document.addEventListener("visibilitychange", refreshWhenVisible);

    return () => {
      active = false;
      window.clearInterval(refreshTimer);
      window.removeEventListener("focus", refreshOnFocus);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, []);

  if (loading) return <div className="card cardPad">Loading dashboard...</div>;
  if (error && !data) return <div className="card cardPad">{error}</div>;

  const stats = [
    {
      title: "Total Appointments",
      value: String(data?.stats?.total_appointments ?? 0),
      subtitle: "From MongoDB",
      icon: <CalendarCheck2 size={19} strokeWidth={2.3} aria-hidden="true" />,
    },
    {
      title: "Active Doctors",
      value: String(data?.stats?.active_doctors ?? 0),
      subtitle: "Currently available",
      icon: <Stethoscope size={19} strokeWidth={2.3} aria-hidden="true" />,
    },
    {
      title: "Voice Calls Today",
      value: String(data?.stats?.calls_today ?? 0),
      subtitle: "Handled by AI",
      icon: <Headphones size={19} strokeWidth={2.3} aria-hidden="true" />,
    },
    {
      title: "System Status",
      value: String(data?.stats?.system_status ?? "Unknown"),
      subtitle: "Backend health",
      icon: <ShieldCheck size={19} strokeWidth={2.3} aria-hidden="true" />,
    },
  ];

  return (
    <div>
      <div className="h1">Dashboard Overview</div>
      <div className="small">
        Live data from backend and MongoDB.{" "}
        {refreshing
          ? "Refreshing..."
          : lastUpdated
            ? `Updated ${formatPakistanTime(lastUpdated)}`
            : ""}
      </div>
      {error ? (
        <div className="small mt8" role="status">
          Refresh failed: {error}. Showing the last successful update.
        </div>
      ) : null}

      <div className="mt16 grid4">
        {stats.map((s) => (
          <StatCard key={s.title} {...s} />
        ))}
      </div>

      <div className="mt16 grid2">
        <ListCard
          title="Upcoming Appointments"
          icon={<CalendarDays size={17} strokeWidth={2.3} aria-hidden="true" />}
          rightAction={<span className="small">Latest</span>}
        >
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

        <ListCard
          title="Recent Voice Calls"
          icon={<PhoneCall size={17} strokeWidth={2.3} aria-hidden="true" />}
          rightAction={<span className="small">{refreshing ? "Updating..." : "Auto-updates"}</span>}
        >
          {(data?.recent_calls || []).length === 0 ? (
            <div className="listRow">No calls yet.</div>
          ) : (
            (data?.recent_calls || []).map((c) => (
              <div key={c.id} className="listRow">
                <div>
                  <div className="listMain">{c.patient_name || "Unknown Caller"}</div>
                  <div className="listSub">Intent: {c.intent || "other"}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div className="listMain">{formatDateTime(c.updated_at || c.created_at)}</div>
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
