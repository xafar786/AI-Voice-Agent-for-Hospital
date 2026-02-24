export default function ListCard({ title, rightAction, icon, children }) {
  return (
    <div className="card">
      <div className="cardHead spread">
        <div className="cardTitle">
          <span>{icon}</span>
          <span>{title}</span>
        </div>
        {rightAction}
      </div>
      <div>{children}</div>
    </div>
  );
}
