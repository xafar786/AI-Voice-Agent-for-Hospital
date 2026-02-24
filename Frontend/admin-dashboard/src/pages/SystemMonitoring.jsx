import { useEffect, useState } from "react";
import Badge from "../components/Badge";
import { api } from "../api/client";

export default function SystemMonitoring() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .getSystemMonitoring()
      .then(setData)
      .catch((err) => setError(err.message || "Failed to load system monitoring"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="card cardPad">Loading system status...</div>;
  if (error) return <div className="card cardPad">{error}</div>;

  return (
    <div>
      <div className="spread">
        <div>
          <div className="h1">System Monitoring</div>
          <div className="small">Real-time backend service and DB status</div>
        </div>
      </div>

      <div className="mt16 card cardPad sysBanner">
        <div>
          <div className="sysTitle">{data?.overall_status || "Unknown"}</div>
          <div className="small">Database: {data?.database_connected ? "Connected" : "Disconnected"}</div>
        </div>

        <div className="sysRight">
          <div className="small">Active Calls</div>
          <div className="sysBig">{data?.active_calls ?? 0}</div>
        </div>
      </div>

      <div className="mt16 sysGrid4">
        {(data?.services || []).map((s) => (
          <div key={s.name} className="card cardPad sysCard">
            <div className="spread">
              <div className="sysCardTitle">{s.name}</div>
              <Badge variant={s.status === "Active" ? "green" : "red"}>{s.status}</Badge>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
