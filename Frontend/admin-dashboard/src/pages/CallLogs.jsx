import { useEffect, useMemo, useState } from "react";
import Badge from "../components/Badge";
import { api, formatDateTime } from "../api/client";

function statusVariant(status) {
  const v = (status || "").toLowerCase();
  if (v.includes("drop") || v.includes("fail")) return "red";
  if (v.includes("progress") || v.includes("pending")) return "yellow";
  return "green";
}

function StatMini({ title, value }) {
  return (
    <div className="card cardPad">
      <div className="small" style={{ fontWeight: 800 }}>{title}</div>
      <div className="statValue" style={{ fontSize: 22 }}>{value}</div>
    </div>
  );
}

export default function CallLogs() {
  const [calls, setCalls] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .getCallLogs()
      .then(setCalls)
      .catch((err) => setError(err.message || "Failed to load call logs"))
      .finally(() => setLoading(false));
  }, []);

  const topStats = useMemo(() => {
    const total = calls.length;
    const completed = calls.filter((c) => (c.status || "").toLowerCase() === "completed").length;
    const successRate = total ? `${Math.round((completed / total) * 100)}%` : "0%";
    return [
      { title: "Total Calls", value: String(total) },
      { title: "Completed", value: String(completed) },
      { title: "Success Rate", value: successRate },
      { title: "Logged Intents", value: String(calls.filter((c) => c.intent && c.intent !== "other").length) },
    ];
  }, [calls]);

  if (loading) return <div className="card cardPad">Loading call logs...</div>;
  if (error) return <div className="card cardPad">{error}</div>;

  return (
    <div>
      <div className="spread">
        <div>
          <div className="h1">Call Records & Transcripts</div>
          <div className="small">MongoDB call log stream from backend</div>
        </div>
      </div>

      <div className="mt16 grid4">
        {topStats.map((s) => (
          <StatMini key={s.title} title={s.title} value={s.value} />
        ))}
      </div>

      <div className="mt16 card tableCard">
        <table className="table">
          <thead>
            <tr>
              <th className="th">Call ID</th>
              <th className="th">Patient</th>
              <th className="th">Date & Time</th>
              <th className="th">Intent</th>
              <th className="th">Transcript</th>
              <th className="th">Status</th>
            </tr>
          </thead>

          <tbody>
            {calls.map((c) => (
              <tr key={c.id} className="tr">
                <td className="td">{c.id}</td>
                <td className="td">
                  <div style={{ fontWeight: 900 }}>{c.patient_name || "Unknown"}</div>
                  <div className="small">{c.phone || "No phone"}</div>
                </td>
                <td className="td">{formatDateTime(c.created_at)}</td>
                <td className="td">{c.intent || "other"}</td>
                <td className="td"><div className="urduPreview">{c.transcript || "-"}</div></td>
                <td className="td">
                  <Badge variant={statusVariant(c.status)}>{c.status || "Completed"}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
