const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8001";

async function request(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      ...(!isFormData ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    const text = await response.text();
    let message = text || `Request failed: ${response.status}`;
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed.detail === "string") message = parsed.detail;
      else if (parsed.detail?.message) message = parsed.detail.message;
      if (parsed.detail?.errors) {
        message = `${message} ${parsed.detail.errors.map((item) => `Row ${item.row}: ${item.error}`).join(" ")}`;
      }
    } catch {
      // Keep the raw response text.
    }
    throw new Error(message);
  }

  return response.json();
}

export const api = {
  getDashboardSummary: () => request("/dashboard/summary"),
  getDoctors: () => request("/doctors"),
  createDoctor: (payload) => request("/doctors", { method: "POST", body: JSON.stringify(payload) }),
  importDoctorsCsv: (file) => {
    const formData = new FormData();
    formData.append("file", file);
    return request("/doctors/bulk-import", { method: "POST", body: formData });
  },
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
  deleteAppointment: (id) => request(`/appointments/${id}`, { method: "DELETE" }),
  getCallLogs: () => request("/call-logs"),
  uploadCallRecording: (sessionId, recordingBlob, durationSeconds) => {
    const formData = new FormData();
    const extension = recordingBlob.type.includes("ogg") ? "ogg" : "webm";
    formData.append("recording", recordingBlob, `call-recording.${extension}`);
    if (Number.isFinite(durationSeconds) && durationSeconds > 0) {
      formData.append("duration_seconds", String(durationSeconds));
    }
    return request(`/call-logs/${encodeURIComponent(sessionId)}/recording`, {
      method: "POST",
      body: formData,
    });
  },
  getCallRecordingUrl: (sessionId) =>
    `${API_BASE}/call-logs/${encodeURIComponent(sessionId)}/recording`,
  getSystemMonitoring: () => request("/system-monitoring"),
  signup: (payload) => request("/auth/signup", { method: "POST", body: JSON.stringify(payload) }),
  login: (payload) => request("/auth/login", { method: "POST", body: JSON.stringify(payload) }),
  forgotPassword: (payload) => request("/auth/forgot-password", { method: "POST", body: JSON.stringify(payload) }),
  getAdminProfile: (username) => request(`/auth/profile/${encodeURIComponent(username)}`),
  updateAdminProfile: (payload) =>
    request("/auth/profile", { method: "PUT", body: JSON.stringify(payload) }),
  changeAdminPassword: (payload) =>
    request("/auth/change-password", { method: "POST", body: JSON.stringify(payload) }),
  uploadAdminPicture: (username, file) => {
    const formData = new FormData();
    formData.append("username", username);
    formData.append("picture", file);
    return request("/auth/profile-picture", { method: "POST", body: formData });
  },
  postTextTurn: ({ transcript, session_id, return_tts = true }) =>
    request("/voice/text-turn", {
      method: "POST",
      body: JSON.stringify({ transcript, session_id, return_tts }),
    }),
  getVoiceGreeting: () => request("/voice/greeting"),
  completeSession: (sessionId) => request(`/sessions/${encodeURIComponent(sessionId)}/complete`, { method: "POST" }),
};

export function formatDateTime(dateValue) {
  if (!dateValue) return "-";
  const date = new Date(dateValue);
  if (Number.isNaN(date.getTime())) return String(dateValue);
  return date.toLocaleString();
}
