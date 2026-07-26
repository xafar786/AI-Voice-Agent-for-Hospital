import unittest

from domain.auth_validation import (
    AuthValidationError,
    normalize_admin_name,
    normalize_admin_username,
    password_rule_results,
    validate_admin_password,
    validate_login_password,
)


class AuthValidationTests(unittest.TestCase):
    def test_valid_admin_credentials_are_normalized(self):
        self.assertEqual(normalize_admin_name("  Ayesha   Khan  "), "Ayesha Khan")
        self.assertEqual(normalize_admin_username(" Admin.User_1 "), "admin.user_1")
        self.assertEqual(
            validate_admin_password("Secure@123", username="admin.user_1"),
            "Secure@123",
        )

    def test_username_requires_safe_format(self):
        invalid_usernames = [
            "abc",
            "1admin",
            "admin user",
            "admin@example.com",
            "a" * 33,
        ]
        for username in invalid_usernames:
            with self.subTest(username=username):
                with self.assertRaises(AuthValidationError):
                    normalize_admin_username(username)

    def test_password_requires_every_security_rule(self):
        invalid_passwords = [
            "Short1!",
            "lowercase1!",
            "UPPERCASE1!",
            "NoNumber!",
            "NoSpecial1",
            "Has Space1!",
            "adminSecure1!",
        ]
        for password in invalid_passwords:
            with self.subTest(password=password):
                with self.assertRaises(AuthValidationError):
                    validate_admin_password(password, username="admin")

    def test_password_rule_results_report_all_requirements(self):
        rules = password_rule_results("Strong@123", username="admin")
        self.assertTrue(all(rules.values()))

    def test_login_accepts_existing_password_without_new_password_rules(self):
        self.assertEqual(validate_login_password("legacy-password"), "legacy-password")
        with self.assertRaises(AuthValidationError):
            validate_login_password("")
        with self.assertRaises(AuthValidationError):
            validate_login_password("x" * 129)

    def test_full_name_requires_letters_and_reasonable_length(self):
        for name in ["A", "12", "A" * 81]:
            with self.subTest(name=name):
                with self.assertRaises(AuthValidationError):
                    normalize_admin_name(name)


if __name__ == "__main__":
    unittest.main()
