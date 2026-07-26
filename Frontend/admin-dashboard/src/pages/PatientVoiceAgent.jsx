import { useNavigate } from "react-router-dom";
import VoiceAgent from "./VoiceAgent";

export default function PatientVoiceAgent() {
  const navigate = useNavigate();

  return (
    <main className="patientVoiceAgentPage">
      <div className="patientVoiceAgentShell">
        <div className="patientHospitalBrand">
          <img src="/shifa-international-hospitals-logo.png" alt="Shifa International Hospitals" />
          <div>
            <strong>AI Voice Agent for Hospital</strong>
            <span>Shifa International Hospital · Patient Service</span>
          </div>
        </div>
        <VoiceAgent onBack={() => navigate("/")} />
      </div>
    </main>
  );
}
