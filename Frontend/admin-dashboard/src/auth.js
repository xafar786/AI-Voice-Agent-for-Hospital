const AUTH_USER_KEY = "voice_agent_admin_user";

export function getCurrentUser() {
  const raw = localStorage.getItem(AUTH_USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function setCurrentUser(user) {
  localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
}

export function clearCurrentUser() {
  localStorage.removeItem(AUTH_USER_KEY);
}

export function isAuthenticated() {
  return Boolean(getCurrentUser());
}
