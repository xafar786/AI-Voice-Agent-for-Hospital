import { Routes, Route, Navigate } from "react-router-dom";
import AdminLayout from "./layout/AdminLayout";
import { isAuthenticated } from "./auth";

import Dashboard from "./pages/Dashboard";
import Doctors from "./pages/Doctors";
import Appointments from "./pages/Appointments";
import Patients from "./pages/Patients";
import CallLogs from "./pages/CallLogs";
import SystemMonitoring from "./pages/SystemMonitoring";
import VoiceAgent from "./pages/VoiceAgent";
import DoctorAvailability from "./pages/DoctorAvailability";
import Login from "./pages/Login";

function ProtectedLayout() {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return <AdminLayout />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to={isAuthenticated() ? "/dashboard" : "/login"} replace />} />
      <Route path="/login" element={<Login />} />

      <Route element={<ProtectedLayout />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/doctors" element={<Doctors />} />
        <Route path="/doctors/:doctorId/availability" element={<DoctorAvailability />} />
        <Route path="/appointments" element={<Appointments />} />
        <Route path="/patients" element={<Patients />} />
        <Route path="/call-logs" element={<CallLogs />} />
        <Route path="/system-monitoring" element={<SystemMonitoring />} />
        <Route path="/voice-agent" element={<VoiceAgent />} />
      </Route>
    </Routes>
  );
}
