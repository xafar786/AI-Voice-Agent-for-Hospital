import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Camera, KeyRound, Pencil, UserRound, X } from "lucide-react";
import { api, formatDateTime } from "../api/client";
import { clearCurrentUser, getCurrentUser, setCurrentUser } from "../auth";
import { getPasswordRules, USERNAME_PATTERN } from "../authRules";

function toLower(value) {
  return String(value || "").toLowerCase();
}

function formatProfileDate(value) {
  return value ? formatDateTime(value) : "Not available";
}

export default function Header() {
  const navigate = useNavigate();
  const [user, setUser] = useState(() => getCurrentUser());
  const name = user?.name || "Admin";
  const username = user?.username || "admin";
  const avatar = (name || "A").trim().slice(0, 1).toUpperCase();

  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);

  const [profileOpen, setProfileOpen] = useState(false);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileMode, setProfileMode] = useState("view");
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileError, setProfileError] = useState("");
  const [profileSuccess, setProfileSuccess] = useState("");
  const [pictureFile, setPictureFile] = useState(null);
  const [profileForm, setProfileForm] = useState({
    name,
    username,
  });
  const [passwordForm, setPasswordForm] = useState({
    oldPassword: "",
    newPassword: "",
    confirmPassword: "",
  });

  const normalizedQuery = useMemo(() => query.trim().toLowerCase(), [query]);
  const passwordRules = useMemo(
    () => getPasswordRules(passwordForm.newPassword, username),
    [passwordForm.newPassword, username],
  );

  useEffect(() => {
    let active = true;
    if (normalizedQuery.length < 2) {
      setResults([]);
      setLoading(false);
      return () => {
        active = false;
      };
    }

    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const [patients, doctors, appointments] = await Promise.all([
          api.getPatients(),
          api.getDoctors(),
          api.getAppointments(),
        ]);
        if (!active) return;

        const patientHits = patients
          .filter((p) =>
            [p.patient_id, p.name, p.phone]
              .filter(Boolean)
              .some((v) => toLower(v).includes(normalizedQuery))
          )
          .slice(0, 4)
          .map((p) => ({
            id: `p-${p.id}`,
            type: "Patient",
            title: p.name || "Unknown Patient",
            subtitle: p.patient_id || p.phone || "",
            path: "/patients",
          }));

        const doctorHits = doctors
          .filter((d) =>
            [d.doctor_id, d.name, d.department, d.specialization, d.qualification]
              .filter(Boolean)
              .some((v) => toLower(v).includes(normalizedQuery))
          )
          .slice(0, 4)
          .map((d) => ({
            id: `d-${d.id}`,
            type: "Doctor",
            title: d.name || "Unknown Doctor",
            subtitle: d.doctor_id || d.department || "",
            path: "/doctors",
          }));

        const appointmentHits = appointments
          .filter((a) =>
            [a.appointment_id, a.patient_name, a.doctor_name, a.scheduled_for]
              .filter(Boolean)
              .some((v) => toLower(v).includes(normalizedQuery))
          )
          .slice(0, 6)
          .map((a) => ({
            id: `a-${a.id}`,
            type: "Appointment",
            title: `${a.patient_name || "Unknown"} / ${a.doctor_name || "Unassigned"}`,
            subtitle: `${a.appointment_id || ""} ${a.scheduled_for || ""}`.trim(),
            path: "/appointments",
          }));

        setResults([...patientHits, ...doctorHits, ...appointmentHits]);
      } catch {
        if (!active) return;
        setResults([]);
      } finally {
        if (active) setLoading(false);
      }
    }, 300);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [normalizedQuery]);

  function syncCurrentUser(updatedUser) {
    setCurrentUser(updatedUser);
    setUser(updatedUser);
    setProfileForm({
      name: updatedUser.name || "",
      username: updatedUser.username || "",
    });
  }

  async function openProfile() {
    setProfileOpen(true);
    setProfileMode("view");
    setProfileError("");
    setProfileSuccess("");
    setProfileLoading(true);
    try {
      const result = await api.getAdminProfile(username);
      syncCurrentUser(result.user);
    } catch (err) {
      setProfileError(err.message || "Unable to load administrator profile.");
    } finally {
      setProfileLoading(false);
    }
  }

  function closeProfile() {
    if (profileSaving) return;
    setProfileOpen(false);
    setProfileError("");
    setProfileSuccess("");
    setPictureFile(null);
  }

  async function handleProfileUpdate(event) {
    event.preventDefault();
    setProfileError("");
    setProfileSuccess("");
    if (profileForm.name.trim().length < 2) {
      setProfileError("Full name must contain at least 2 characters.");
      return;
    }
    if (!USERNAME_PATTERN.test(profileForm.username.trim())) {
      setProfileError(
        "Username must be 4–32 characters, start with a letter, and use only letters, numbers, dots, underscores, or hyphens.",
      );
      return;
    }
    setProfileSaving(true);
    try {
      const result = await api.updateAdminProfile({
        current_username: username,
        name: profileForm.name,
        username: profileForm.username,
      });
      syncCurrentUser(result.user);
      setProfileSuccess("Administrator details updated successfully.");
      setProfileMode("view");
    } catch (err) {
      setProfileError(err.message || "Unable to update administrator details.");
    } finally {
      setProfileSaving(false);
    }
  }

  async function handlePasswordChange(event) {
    event.preventDefault();
    setProfileError("");
    setProfileSuccess("");
    if (!passwordForm.oldPassword) {
      setProfileError("Enter your current password.");
      return;
    }
    const failedRule = passwordRules.find((rule) => !rule.passed);
    if (failedRule) {
      setProfileError(`Password requirement not met: ${failedRule.label}.`);
      return;
    }
    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      setProfileError("New password and confirmation password do not match.");
      return;
    }
    setProfileSaving(true);
    try {
      await api.changeAdminPassword({
        username,
        old_password: passwordForm.oldPassword,
        new_password: passwordForm.newPassword,
      });
      setPasswordForm({ oldPassword: "", newPassword: "", confirmPassword: "" });
      setProfileSuccess("Password changed successfully.");
      setProfileMode("view");
    } catch (err) {
      setProfileError(err.message || "Unable to change password.");
    } finally {
      setProfileSaving(false);
    }
  }

  async function handlePictureUpload(event) {
    event.preventDefault();
    setProfileError("");
    setProfileSuccess("");
    if (!pictureFile) {
      setProfileError("Select a JPG, PNG, or WebP profile picture.");
      return;
    }
    if (!["image/jpeg", "image/png", "image/webp"].includes(pictureFile.type)) {
      setProfileError("Profile picture must be a JPG, PNG, or WebP image.");
      return;
    }
    if (pictureFile.size > 2 * 1024 * 1024) {
      setProfileError("Profile picture must not exceed 2 MB.");
      return;
    }
    setProfileSaving(true);
    try {
      const result = await api.uploadAdminPicture(username, pictureFile);
      syncCurrentUser(result.user);
      setPictureFile(null);
      setProfileSuccess("Profile picture updated successfully.");
    } catch (err) {
      setProfileError(err.message || "Unable to upload profile picture.");
    } finally {
      setProfileSaving(false);
    }
  }

  function handleLogout() {
    clearCurrentUser();
    navigate("/login", { replace: true });
  }

  function handleSelect(path) {
    setOpen(false);
    navigate(path);
  }

  function renderAvatar(className = "avatar") {
    return (
      <span className={className}>
        {user?.profile_picture ? (
          <img src={user.profile_picture} alt={`${name} profile`} />
        ) : (
          avatar
        )}
      </span>
    );
  }

  return (
    <>
      <header className="header">
        <div className="headerLeft">
          <div className="title">AI Voice Agent for Hospital</div>
          <div className="sub">Admin Dashboard</div>
        </div>

        <div className="searchWrap">
          <input
            className="search"
            placeholder="Search patients, doctors, appointments..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setOpen(true)}
          />
          {open && query.trim().length > 0 && (
            <div className="searchDropdown">
              {loading && <div className="searchItem searchMeta">Searching...</div>}
              {!loading && results.length === 0 && <div className="searchItem searchMeta">No results</div>}
              {!loading &&
                results.map((item) => (
                  <button key={item.id} className="searchItem" type="button" onClick={() => handleSelect(item.path)}>
                    <div className="searchType">{item.type}</div>
                    <div className="searchMain">{item.title}</div>
                    <div className="searchSub">{item.subtitle}</div>
                  </button>
                ))}
            </div>
          )}
        </div>

        <div className="row gap12">
          <button className="profile profileButton" type="button" onClick={openProfile}>
            <span className="profileTxt">
              <span className="name">{name}</span>
              <span className="role">@{username}</span>
            </span>
            {renderAvatar()}
          </button>
          <button className="btn" onClick={handleLogout} type="button">Logout</button>
        </div>
      </header>

      {profileOpen && (
        <div className="modalBackdrop adminProfileBackdrop" onMouseDown={closeProfile}>
          <section
            className="modalCard adminProfileModal"
            role="dialog"
            aria-modal="true"
            aria-label="Administrator profile"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <button className="adminProfileClose" type="button" onClick={closeProfile} aria-label="Close profile">
              <X size={19} aria-hidden="true" />
            </button>

            <div className="adminProfileHero">
              <div className="adminProfileAvatarWrap">
                {renderAvatar("adminProfileAvatar")}
                <span className="adminProfileCamera" aria-hidden="true">
                  <Camera size={15} />
                </span>
              </div>
              <div>
                <span className="adminProfileEyebrow">Administrator Profile</span>
                <h2>{name}</h2>
                <p>@{username}</p>
              </div>
            </div>

            {profileError && <div className="authMsg authErr">{profileError}</div>}
            {profileSuccess && <div className="authMsg authOk">{profileSuccess}</div>}

            {profileLoading ? (
              <div className="adminProfileLoading">Loading administrator details...</div>
            ) : (
              <>
                {profileMode === "view" && (
                  <div className="adminProfileBody">
                    <div className="adminProfileDetails">
                      <div>
                        <span>Administrator ID</span>
                        <strong>{user?.admin_id || "Not available"}</strong>
                      </div>
                      <div>
                        <span>Full Name</span>
                        <strong>{name}</strong>
                      </div>
                      <div>
                        <span>Username</span>
                        <strong>@{username}</strong>
                      </div>
                      <div>
                        <span>Account Created</span>
                        <strong>{formatProfileDate(user?.created_at)}</strong>
                      </div>
                      <div>
                        <span>Last Updated</span>
                        <strong>{formatProfileDate(user?.updated_at)}</strong>
                      </div>
                    </div>

                    <form className="adminPictureForm" onSubmit={handlePictureUpload}>
                      <label>
                        <Camera size={17} aria-hidden="true" />
                        <span>{pictureFile ? pictureFile.name : "Choose profile picture"}</span>
                        <input
                          type="file"
                          accept="image/jpeg,image/png,image/webp"
                          onChange={(event) => setPictureFile(event.target.files?.[0] || null)}
                        />
                      </label>
                      <span>JPG, PNG or WebP · Maximum 2 MB</span>
                      <button className="btn" type="submit" disabled={!pictureFile || profileSaving}>
                        Upload Picture
                      </button>
                    </form>

                    <div className="adminProfileActions">
                      <button className="btn btnPrimary" type="button" onClick={() => {
                        setProfileError("");
                        setProfileSuccess("");
                        setProfileMode("edit");
                      }}>
                        <Pencil size={15} aria-hidden="true" /> Edit Details
                      </button>
                      <button className="btn" type="button" onClick={() => {
                        setProfileError("");
                        setProfileSuccess("");
                        setProfileMode("password");
                      }}>
                        <KeyRound size={15} aria-hidden="true" /> Change Password
                      </button>
                    </div>
                  </div>
                )}

                {profileMode === "edit" && (
                  <form className="adminProfileForm" onSubmit={handleProfileUpdate}>
                    <div className="adminProfileFormTitle">
                      <UserRound size={18} aria-hidden="true" />
                      Edit administrator details
                    </div>
                    <label>
                      Full Name
                      <input
                        className="hospitalAuthInput"
                        value={profileForm.name}
                        onChange={(event) => setProfileForm((prev) => ({ ...prev, name: event.target.value }))}
                        minLength={2}
                        maxLength={80}
                        required
                      />
                    </label>
                    <label>
                      Username
                      <input
                        className="hospitalAuthInput"
                        value={profileForm.username}
                        onChange={(event) => setProfileForm((prev) => ({ ...prev, username: event.target.value }))}
                        minLength={4}
                        maxLength={32}
                        pattern="[A-Za-z][A-Za-z0-9._-]{3,31}"
                        required
                      />
                    </label>
                    <div className="adminProfileActions">
                      <button className="btn" type="button" onClick={() => setProfileMode("view")}>Cancel</button>
                      <button className="btn btnPrimary" type="submit" disabled={profileSaving}>
                        {profileSaving ? "Saving..." : "Save Changes"}
                      </button>
                    </div>
                  </form>
                )}

                {profileMode === "password" && (
                  <form className="adminProfileForm" onSubmit={handlePasswordChange}>
                    <div className="adminProfileFormTitle">
                      <KeyRound size={18} aria-hidden="true" />
                      Change password
                    </div>
                    <label>
                      Current Password
                      <input
                        className="hospitalAuthInput"
                        type="password"
                        value={passwordForm.oldPassword}
                        onChange={(event) => setPasswordForm((prev) => ({ ...prev, oldPassword: event.target.value }))}
                        autoComplete="current-password"
                        maxLength={128}
                        required
                      />
                    </label>
                    <label>
                      New Password
                      <input
                        className="hospitalAuthInput"
                        type="password"
                        value={passwordForm.newPassword}
                        onChange={(event) => setPasswordForm((prev) => ({ ...prev, newPassword: event.target.value }))}
                        autoComplete="new-password"
                        maxLength={128}
                        required
                      />
                    </label>
                    <div className="hospitalPasswordRules" aria-label="Password requirements">
                      {passwordRules.map((rule) => (
                        <span className={rule.passed ? "hospitalPasswordRulePassed" : ""} key={rule.label}>
                          <i aria-hidden="true">{rule.passed ? "✓" : "•"}</i>
                          {rule.label}
                        </span>
                      ))}
                    </div>
                    <label>
                      Confirm New Password
                      <input
                        className="hospitalAuthInput"
                        type="password"
                        value={passwordForm.confirmPassword}
                        onChange={(event) => setPasswordForm((prev) => ({ ...prev, confirmPassword: event.target.value }))}
                        autoComplete="new-password"
                        maxLength={128}
                        required
                      />
                    </label>
                    <div className="adminProfileActions">
                      <button className="btn" type="button" onClick={() => setProfileMode("view")}>Cancel</button>
                      <button className="btn btnPrimary" type="submit" disabled={profileSaving}>
                        {profileSaving ? "Changing..." : "Change Password"}
                      </button>
                    </div>
                  </form>
                )}
              </>
            )}
          </section>
        </div>
      )}
    </>
  );
}
