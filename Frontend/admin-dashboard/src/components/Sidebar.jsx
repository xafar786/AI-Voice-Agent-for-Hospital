import { NavLink } from "react-router-dom";

const Item = ({ to, label, icon }) => (
  <NavLink className={({ isActive }) => (isActive ? "navLink active" : "navLink")} to={to}>
    <span style={{ width: 28, display: "inline-grid", placeItems: "center", fontSize: 11, fontWeight: 800 }}>{icon}</span>
    <span>{label}</span>
  </NavLink>
);

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brandIcon">VA</div>
        <div>
          <div className="brandTitle">AI Voice Agent</div>
          <div className="brandSub">Hospital (Urdu)</div>
        </div>
      </div>

      <nav className="nav">
        <Item to="/dashboard" label="Dashboard Overview" icon="DB" />
        <Item to="/voice-agent" label="Live Voice Agent" icon="MIC" />
        <Item to="/doctors" label="Doctor Management" icon="DR" />
        <Item to="/appointments" label="Appointment Management" icon="APT" />
        <Item to="/patients" label="Patient Records" icon="PT" />
        <Item to="/call-logs" label="Call Records & Transcripts" icon="LOG" />
        <Item to="/system-monitoring" label="System Monitoring" icon="SYS" />
      </nav>

      <div className="navFooter">Collapse</div>
    </aside>
  );
}
