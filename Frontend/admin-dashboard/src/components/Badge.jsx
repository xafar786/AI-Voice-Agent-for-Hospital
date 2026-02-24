export default function Badge({ variant, children }) {
  const map = {
    green: "badge bGreen",
    yellow: "badge bYellow",
    blue: "badge bBlue",
    red: "badge bRed",
    gray: "badge bGray",
  };

  return <span className={map[variant] || "badge"}>{children}</span>;
}
