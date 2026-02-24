const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8001";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }

  return response.json();
}

export const api = {
  getDashboardSummary: () => request("/dashboard/summary"),
  getDoctors: () => request("/doctors"),
  createDoctor: (payload) => request("/doctors", { method: "POST", body: JSON.stringify(payload) }),
  updateDoctor: (id, payload) => request(`/doctors/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteDoctor: (id) => request(`/doctors/${id}`, { method: "DELETE" }),
  getPatients: () => request("/patients"),
  createPatient: (payload) => request("/patients", { method: "POST", body: JSON.stringify(payload) }),
  updatePatient: (id, payload) => request(`/patients/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deletePatient: (id) => request(`/patients/${id}`, { method: "DELETE" }),
  getPatientAppointments: (id) => request(`/patients/${id}/appointments`),
  getAppointments: () => request("/appointments"),
  createManualAppointment: (payload) => request("/appointments/manual", { method: "POST", body: JSON.stringify(payload) }),
  updateAppointment: (id, payload) => request(`/appointments/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  cancelAppointment: (id) => request(`/appointments/${id}/cancel`, { method: "POST" }),
  getCallLogs: () => request("/call-logs"),
  getSystemMonitoring: () => request("/system-monitoring"),
  signup: (payload) => request("/auth/signup", { method: "POST", body: JSON.stringify(payload) }),
  login: (payload) => request("/auth/login", { method: "POST", body: JSON.stringify(payload) }),
  forgotPassword: (payload) => request("/auth/forgot-password", { method: "POST", body: JSON.stringify(payload) }),
  postTextTurn: ({ transcript, session_id, return_tts = true }) =>
    request("/voice/text-turn", {
      method: "POST",
      body: JSON.stringify({ transcript, session_id, return_tts }),
    }),
};

export function formatDateTime(dateValue) {
  if (!dateValue) return "-";
  const date = new Date(dateValue);
  if (Number.isNaN(date.getTime())) return String(dateValue);
  return date.toLocaleString();
}
