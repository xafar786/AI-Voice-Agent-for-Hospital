import { NavLink } from "react-router-dom";
import {
  Activity,
  CalendarDays,
  LayoutDashboard,
  PhoneCall,
  Stethoscope,
  Users,
} from "lucide-react";

const Item = ({ to, label, icon }) => (
  <NavLink className={({ isActive }) => (isActive ? "navLink active" : "navLink")} to={to}>
    <span className="navIcon" aria-hidden="true">
      {icon}
    </span>
    <span>{label}</span>
  </NavLink>
);

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brandLogo">
          <img
            src="/shifa-international-hospitals-logo.png"
            alt="Shifa International Hospitals"
          />
        </div>
        <div className="brandMeta">
          <span aria-hidden="true" />
          <div>
            <div className="brandTitle">AI Voice Agent</div>
            <div className="brandSub">Admin Dashboard</div>
          </div>
        </div>
      </div>

      <nav className="nav">
        <Item to="/dashboard" label="Dashboard Overview" icon={<LayoutDashboard size={18} strokeWidth={2.2} />} />
        <Item to="/doctors" label="Doctor Management" icon={<Stethoscope size={18} strokeWidth={2.2} />} />
        <Item to="/appointments" label="Appointment Management" icon={<CalendarDays size={18} strokeWidth={2.2} />} />
        <Item to="/patients" label="Patient Records" icon={<Users size={18} strokeWidth={2.2} />} />
        <Item to="/call-logs" label="Call Records & Transcripts" icon={<PhoneCall size={18} strokeWidth={2.2} />} />
        <Item to="/system-monitoring" label="System Monitoring" icon={<Activity size={18} strokeWidth={2.2} />} />
      </nav>

      <div className="navFooter">Collapse</div>
    </aside>
  );
}
