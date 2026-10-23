"""Run against an isolated MariaDB whose database name ends in _test."""

import os
import secrets
import unittest

from fastapi.testclient import TestClient
import pymysql

from backend.app import app


class AccountIntegrationTest(unittest.TestCase):
    def setUp(self):
        database = os.getenv("KERVION_DB_NAME", "")
        if not database.endswith("_test"):
            self.skipTest("KERVION_DB_NAME must end in _test")
        self.username = "auth_test_" + secrets.token_hex(6)
        self.other_username = "other_test_" + secrets.token_hex(6)
        self.origin = {"Origin": "http://127.0.0.1:8010"}
        self.password = "an isolated test password"
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        if hasattr(self, "client"):
            self.client.__exit__(None, None, None)
        if not hasattr(self, "username"):
            return
        with pymysql.connect(
            host=os.getenv("KERVION_DB_HOST", "127.0.0.1"),
            port=int(os.getenv("KERVION_DB_PORT", "3306")),
            user=os.getenv("KERVION_DB_USER", "kervion"),
            password=os.getenv("KERVION_DB_PASSWORD", ""),
            database=os.getenv("KERVION_DB_NAME", ""),
            autocommit=True,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM saves WHERE user_id IN "
                    "(SELECT user_id FROM users WHERE username IN (%s, %s))",
                    (self.username, self.other_username),
                )
                cursor.execute("DELETE FROM users WHERE username=%s", (self.username,))
                cursor.execute("DELETE FROM users WHERE username=%s", (self.other_username,))

    def test_signup_session_login_and_save_list(self):
        signup = self.client.post(
            "/api/v1/auth/signup",
            json={"username": self.username, "password": self.password, "role": "std"},
            headers=self.origin,
        )
        self.assertEqual(signup.status_code, 201, signup.text)
        self.assertEqual(signup.json()["roles"], ["std"])
        self.assertIn("httponly", signup.headers["set-cookie"].lower())
        self.assertEqual(self.client.get("/api/v1/auth/me").json()["username"], self.username)
        self.assertEqual(self.client.get("/api/v1/saves").json(), {"saves": []})

        with pymysql.connect(
            host=os.getenv("KERVION_DB_HOST", "127.0.0.1"),
            port=int(os.getenv("KERVION_DB_PORT", "3306")),
            user=os.getenv("KERVION_DB_USER", "kervion"),
            password=os.getenv("KERVION_DB_PASSWORD", ""),
            database=os.getenv("KERVION_DB_NAME", ""),
            autocommit=True,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                    (self.other_username, "isolated-test-only"),
                )
                cursor.execute(
                    "INSERT INTO saves (user_id, slot_no, role, day) VALUES (%s, 1, 'std', 1)",
                    (cursor.lastrowid,),
                )
        self.assertEqual(self.client.get("/api/v1/saves").json(), {"saves": []})

        with pymysql.connect(
            host=os.getenv("KERVION_DB_HOST", "127.0.0.1"),
            port=int(os.getenv("KERVION_DB_PORT", "3306")),
            user=os.getenv("KERVION_DB_USER", "kervion"),
            password=os.getenv("KERVION_DB_PASSWORD", ""),
            database=os.getenv("KERVION_DB_NAME", ""),
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT password_hash FROM users WHERE username=%s", (self.username,)
                )
                stored = cursor.fetchone()[0]
                self.assertTrue(stored.startswith("scrypt$"))
                self.assertNotIn(self.password, stored)
                cursor.execute(
                    "SELECT COUNT(*) FROM auth_sessions WHERE user_id="
                    "(SELECT user_id FROM users WHERE username=%s)",
                    (self.username,),
                )
                self.assertEqual(cursor.fetchone()[0], 1)

        duplicate = self.client.post(
            "/api/v1/auth/signup",
            json={"username": self.username, "password": self.password, "role": "std"},
            headers=self.origin,
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["error"]["code"], "STATE_CONFLICT")
        self.assertIn("request_id", duplicate.json()["error"])

        forbidden = self.client.post(
            "/api/v1/auth/logout", headers={"Origin": "https://evil.example"}
        )
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 200)

        self.assertEqual(
            self.client.post("/api/v1/auth/logout", headers=self.origin).status_code,
            204,
        )
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 401)
        wrong = self.client.post(
            "/api/v1/auth/login",
            json={"username": self.username, "password": "wrong password"},
            headers=self.origin,
        )
        self.assertEqual(wrong.status_code, 401)
        correct = self.client.post(
            "/api/v1/auth/login",
            json={"username": self.username, "password": self.password},
            headers=self.origin,
        )
        self.assertEqual(correct.status_code, 200, correct.text)
        self.assertEqual(self.client.get("/api/v1/auth/me").status_code, 200)


if __name__ == "__main__":
    unittest.main()
