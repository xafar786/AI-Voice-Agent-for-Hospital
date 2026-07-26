import { useMemo, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { isAuthenticated, setCurrentUser } from "../auth";
import { getPasswordRules, USERNAME_PATTERN } from "../authRules";

const MODES = {
  login: "login",
  signup: "signup",
  forgot: "forgot",
};

export default function Login() {
  const navigate = useNavigate();
  const [mode, setMode] = useState(MODES.login);
  const [form, setForm] = useState({
    name: "",
    username: "",
    password: "",
    code: "",
    newPassword: "",
    confirmPassword: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const pageContent = useMemo(() => {
    if (mode === MODES.signup) {
      return {
        eyebrow: "Administrator Registration",
        title: "Create your admin account",
        description: "Register securely to manage Shifa’s hospital voice-agent operations.",
        submit: "Create Admin Account",
      };
    }
    if (mode === MODES.forgot) {
      return {
        eyebrow: "Account Recovery",
        title: "Reset your password",
        description: "Verify your security code and choose a new administrator password.",
        submit: "Reset Password",
      };
    }
    return {
      eyebrow: "Secure Administration Portal",
      title: "Welcome back",
      description: "Sign in to access the Shifa AI Voice Agent administration dashboard.",
      submit: "Sign In to Dashboard",
    };
  }, [mode]);

  const activeNewPassword = mode === MODES.signup ? form.password : form.newPassword;
  const passwordRules = useMemo(
    () => getPasswordRules(activeNewPassword, form.username),
    [activeNewPassword, form.username],
  );

  if (isAuthenticated()) {
    return <Navigate to="/dashboard" replace />;
  }

  function resetMessages() {
    setError("");
    setSuccess("");
  }

  async function onSubmit(e) {
    e.preventDefault();
    resetMessages();

    if (mode !== MODES.login) {
      if (!USERNAME_PATTERN.test(form.username.trim())) {
        setError(
          "Username must be 4–32 characters, start with a letter, and use only letters, numbers, dots, underscores, or hyphens.",
        );
        return;
      }
      if (mode === MODES.signup && form.name.trim().length < 2) {
        setError("Full name must contain at least 2 characters.");
        return;
      }
      const failedPasswordRule = passwordRules.find((rule) => !rule.passed);
      if (failedPasswordRule) {
        setError(`Password requirement not met: ${failedPasswordRule.label}.`);
        return;
      }
      if (activeNewPassword !== form.confirmPassword) {
        setError("Password and confirmation password do not match.");
        return;
      }
    }

    setLoading(true);
    try {
      if (mode === MODES.login) {
        const result = await api.login({
          username: form.username,
          password: form.password,
        });
        setCurrentUser(result.user);
        navigate("/dashboard", { replace: true });
        return;
      }

      if (mode === MODES.signup) {
        await api.signup({
          name: form.name,
          username: form.username,
          password: form.password,
          code: form.code,
        });
        setSuccess("Signup successful. You can now login.");
        setMode(MODES.login);
        setForm((prev) => ({ ...prev, password: "", confirmPassword: "", code: "" }));
        return;
      }

      await api.forgotPassword({
        username: form.username,
        code: form.code,
        new_password: form.newPassword,
      });
      setSuccess("Password reset successful. Login with your new password.");
      setMode(MODES.login);
      setForm((prev) => ({
        ...prev,
        password: "",
        newPassword: "",
        confirmPassword: "",
        code: "",
      }));
    } catch (err) {
      setError(err.message || "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="hospitalAuthPage">
      <section className="hospitalAuthShell">
        <aside className="hospitalAuthBrandPanel">
          <div className="hospitalAuthBrandTop">
            <div className="hospitalAuthLogoPlate">
              <img src="/shifa-international-hospitals-logo.png" alt="Shifa International Hospitals" />
            </div>
            <span>Hospital AI Platform</span>
          </div>

          <div className="hospitalAuthHero">
            <div className="hospitalAuthPulse" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            <div className="hospitalAuthKicker">Shifa International Hospital</div>
            <h1>AI Voice Agent<br />for Hospital</h1>
            <p>
              A secure administration workspace for managing appointments,
              patients, doctors, and intelligent Urdu voice interactions.
            </p>
          </div>

          <div className="hospitalAuthTrust">
            <span aria-hidden="true">+</span>
            Secure hospital administration access
          </div>
        </aside>

        <section className="hospitalAuthFormPanel">
          <button className="hospitalAuthBack" type="button" onClick={() => navigate("/")}>
            <span aria-hidden="true">←</span> Back to modules
          </button>

          <div className="hospitalAuthMobileLogo">
            <img src="/shifa-international-hospitals-logo.png" alt="Shifa International Hospitals" />
          </div>

          <div className="hospitalAuthFormWrap">
            <div className="hospitalAuthEyebrow">{pageContent.eyebrow}</div>
            <h2>{pageContent.title}</h2>
            <p className="hospitalAuthDescription">{pageContent.description}</p>

            {error && <div className="authMsg authErr mt16">{error}</div>}
            {success && <div className="authMsg authOk mt16">{success}</div>}

            <form className="hospitalAuthForm" onSubmit={onSubmit}>
              {mode === MODES.signup && (
                <label>
                  Full Name
                  <input
                    className="hospitalAuthInput"
                    value={form.name}
                    onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
                    placeholder="Enter administrator name"
                    autoComplete="name"
                    minLength={2}
                    maxLength={80}
                    required
                  />
                </label>
              )}

              <label>
                Username
                <input
                  className="hospitalAuthInput"
                  value={form.username}
                  onChange={(e) => setForm((prev) => ({ ...prev, username: e.target.value }))}
                  placeholder="Enter your username"
                  autoComplete="username"
                  minLength={mode === MODES.login ? undefined : 4}
                  maxLength={32}
                  pattern={mode === MODES.login ? undefined : "[A-Za-z][A-Za-z0-9._-]{3,31}"}
                  title="Start with a letter and use 4–32 letters, numbers, dots, underscores, or hyphens."
                  required
                />
                {mode !== MODES.login && (
                  <span className="hospitalAuthFieldHint">
                    4–32 characters; start with a letter. Letters, numbers, dots, underscores, and hyphens only.
                  </span>
                )}
              </label>

              {mode !== MODES.forgot && (
                <label>
                  Password
                  <input
                    className="hospitalAuthInput"
                    type="password"
                    value={form.password}
                    onChange={(e) => setForm((prev) => ({ ...prev, password: e.target.value }))}
                    placeholder="Enter your password"
                    autoComplete={mode === MODES.login ? "current-password" : "new-password"}
                    maxLength={128}
                    required
                  />
                </label>
              )}

              {mode === MODES.forgot && (
                <label>
                  New Password
                  <input
                    className="hospitalAuthInput"
                    type="password"
                    value={form.newPassword}
                    onChange={(e) => setForm((prev) => ({ ...prev, newPassword: e.target.value }))}
                    placeholder="Create a new password"
                    autoComplete="new-password"
                    maxLength={128}
                    required
                  />
                </label>
              )}

              {mode !== MODES.login && (
                <>
                  <div className="hospitalPasswordRules" aria-label="Password requirements">
                    {passwordRules.map((rule) => (
                      <span
                        className={rule.passed ? "hospitalPasswordRulePassed" : ""}
                        key={rule.label}
                      >
                        <i aria-hidden="true">{rule.passed ? "✓" : "•"}</i>
                        {rule.label}
                      </span>
                    ))}
                  </div>
                  <label>
                    Confirm Password
                    <input
                      className="hospitalAuthInput"
                      type="password"
                      value={form.confirmPassword}
                      onChange={(e) => setForm((prev) => ({ ...prev, confirmPassword: e.target.value }))}
                      placeholder="Enter the password again"
                      autoComplete="new-password"
                      maxLength={128}
                      required
                    />
                  </label>
                </>
              )}

              {mode !== MODES.login && (
                <label>
                  Security Code
                  <input
                    className="hospitalAuthInput"
                    value={form.code}
                    onChange={(e) => setForm((prev) => ({ ...prev, code: e.target.value }))}
                    placeholder="Enter the hospital security code"
                    autoComplete="one-time-code"
                    maxLength={64}
                    required
                  />
                </label>
              )}

              <button className="hospitalAuthSubmit" type="submit" disabled={loading}>
                {loading ? "Please wait..." : pageContent.submit}
              </button>
            </form>

            <div className="hospitalAuthModeLinks">
              {mode === MODES.login && (
                <>
                  <span>New administrator?</span>
                  <button onClick={() => { resetMessages(); setMode(MODES.signup); }} type="button">
                    Create an account
                  </button>
                  <button className="hospitalAuthForgot" onClick={() => { resetMessages(); setMode(MODES.forgot); }} type="button">
                    Forgot password?
                  </button>
                </>
              )}
              {mode !== MODES.login && (
                <>
                  <span>Already have an account?</span>
                  <button onClick={() => { resetMessages(); setMode(MODES.login); }} type="button">
                    Return to sign in
                  </button>
                </>
              )}
            </div>

            <div className="hospitalAuthPrivacy">
              Authorized Shifa International Hospital administrators only.
            </div>
          </div>
        </section>
      </section>
    </main>
  );
}
