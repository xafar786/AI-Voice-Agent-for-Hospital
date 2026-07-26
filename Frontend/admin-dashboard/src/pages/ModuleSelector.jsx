import { Link } from "react-router-dom";

export default function ModuleSelector() {
  return (
    <main className="moduleSelectorPage">
      <section className="moduleSelectorShell" aria-labelledby="module-selector-title">
        <header className="moduleSelectorHeader">
          <div className="moduleSelectorLogo">
            <img
              src="/shifa-international-hospitals-logo.png"
              alt="Shifa International Hospitals"
            />
          </div>
          <div className="moduleSelectorHeaderCopy">
            <span>AI Voice Agent for Hospital</span>
            <strong>Shifa International Hospital</strong>
          </div>
          <div className="moduleSelectorStatus">
            <i aria-hidden="true" />
            Services Online
          </div>
        </header>

        <div className="moduleSelectorIntro">
          <span className="moduleSelectorEyebrow">Welcome to Shifa Digital Care</span>
          <h1 id="module-selector-title">How would you like to continue?</h1>
        </div>

        <div className="moduleSelectorGrid">
          <Link className="moduleChoiceCard moduleChoicePatient" to="/patient/voice-agent">
            <span className="moduleChoiceTop">
              <span className="moduleChoiceIcon" aria-hidden="true">🎙</span>
            </span>
            <span className="moduleChoiceContent">
              <span>Patient Services</span>
              <strong>Live Voice Agent</strong>
              <small>Speak with Shifa Hospital’s voice assistant for appointments, cancellations, and doctor availability.</small>
            </span>
            <span className="moduleChoiceAction">Start Voice Assistant <span aria-hidden="true">→</span></span>
          </Link>

          <Link className="moduleChoiceCard moduleChoiceAdmin" to="/admin">
            <span className="moduleChoiceTop">
              <span className="moduleChoiceIcon" aria-hidden="true">✚</span>
            </span>
            <span className="moduleChoiceContent">
              <span>Hospital Administration</span>
              <strong>Admin Dashboard</strong>
              <small>Manage doctors, appointments, patients, call records, availability, and system monitoring.</small>
            </span>
            <span className="moduleChoiceAction">Continue to Admin Login <span aria-hidden="true">→</span></span>
          </Link>
        </div>

        <footer className="moduleSelectorFooter">
          <span>© Shifa International Hospitals Ltd.</span>
        </footer>
      </section>
    </main>
  );
}
