import { useMemo, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { isAuthenticated, setCurrentUser } from "../auth";

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
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const title = useMemo(() => {
    if (mode === MODES.signup) return "Admin Sign Up";
    if (mode === MODES.forgot) return "Forgot Password";
    return "Admin Login";
  }, [mode]);

  if (isAuthenticated()) {
    return <Navigate to="/dashboard" replace />;
  }

  function resetMessages() {
    setError("");
    setSuccess("");
  }

  async function onSubmit(e) {
    e.preventDefault();
    setLoading(true);
    resetMessages();

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
        setForm((prev) => ({ ...prev, password: "", code: "" }));
        return;
      }

      await api.forgotPassword({
        username: form.username,
        code: form.code,
        new_password: form.newPassword,
      });
      setSuccess("Password reset successful. Login with your new password.");
      setMode(MODES.login);
      setForm((prev) => ({ ...prev, password: "", newPassword: "", code: "" }));
    } catch (err) {
      setError(err.message || "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="authPage">
      <div className="authCard">
        <div className="h1">{title}</div>
        <div className="small mt12">Use username/password. Signup and reset require a secret security code.</div>

        {error && <div className="authMsg authErr mt12">{error}</div>}
        {success && <div className="authMsg authOk mt12">{success}</div>}

        <form className="mt16 authForm" onSubmit={onSubmit}>
          {mode === MODES.signup && (
            <label className="small">
              Name
              <input
                className="input authInput"
                value={form.name}
                onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
                required
              />
            </label>
          )}

          <label className="small">
            Username
            <input
              className="input authInput"
              value={form.username}
              onChange={(e) => setForm((prev) => ({ ...prev, username: e.target.value }))}
              required
            />
          </label>

          {mode !== MODES.forgot && (
            <label className="small">
              Password
              <input
                className="input authInput"
                type="password"
                value={form.password}
                onChange={(e) => setForm((prev) => ({ ...prev, password: e.target.value }))}
                required
              />
            </label>
          )}

          {mode === MODES.forgot && (
            <label className="small">
              New Password
              <input
                className="input authInput"
                type="password"
                value={form.newPassword}
                onChange={(e) => setForm((prev) => ({ ...prev, newPassword: e.target.value }))}
                required
              />
            </label>
          )}

          {mode !== MODES.login && (
            <label className="small">
              Code
              <input
                className="input authInput"
                value={form.code}
                onChange={(e) => setForm((prev) => ({ ...prev, code: e.target.value }))}
                required
              />
            </label>
          )}

          <button className="btn btnPrimary" type="submit" disabled={loading}>
            {loading ? "Please wait..." : "Submit"}
          </button>
        </form>

        <div className="authLinks mt16">
          <button className="linkBtn" onClick={() => { resetMessages(); setMode(MODES.login); }} type="button">Login</button>
          <button className="linkBtn" onClick={() => { resetMessages(); setMode(MODES.signup); }} type="button">Sign Up</button>
          <button className="linkBtn" onClick={() => { resetMessages(); setMode(MODES.forgot); }} type="button">Forgot Password</button>
        </div>
      </div>
    </div>
  );
}
