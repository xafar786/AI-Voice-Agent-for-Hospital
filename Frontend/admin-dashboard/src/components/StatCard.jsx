export default function StatCard({ title, value, subtitle, icon, badge }) {
  return (
    <div className="card cardPad">
      <div className="statTop">
        <div>
          <div className="small" style={{ fontWeight: 800 }}>{title}</div>
          <div className="statValue">{value}</div>
          <div className="statSub">{subtitle}</div>
          {badge && <div className="small" style={{ marginTop: 6, color: "#16a34a", fontWeight: 800 }}>{badge}</div>}
        </div>
        <div className="pillIcon">{icon}</div>
      </div>
    </div>
  );
}
