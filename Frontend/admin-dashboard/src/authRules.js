export const USERNAME_PATTERN = /^[A-Za-z][A-Za-z0-9._-]{3,31}$/;

export function getPasswordRules(password, username) {
  const value = String(password || "");
  const normalizedUsername = String(username || "").trim().toLowerCase();
  return [
    { label: "8–128 characters", passed: value.length >= 8 && value.length <= 128 },
    { label: "One uppercase letter", passed: /[A-Z]/.test(value) },
    { label: "One lowercase letter", passed: /[a-z]/.test(value) },
    { label: "One number", passed: /\d/.test(value) },
    { label: "One special character", passed: /[^A-Za-z0-9\s]/.test(value) },
    { label: "No spaces", passed: !/\s/.test(value) },
    {
      label: "Does not contain username",
      passed: !normalizedUsername || !value.toLowerCase().includes(normalizedUsername),
    },
  ];
}
