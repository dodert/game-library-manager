"""Optional login: one user and password from AUTH_USERNAME / AUTH_PASSWORD, no user management.

A successful login sets a signed cookie (HMAC, no server-side sessions). The signing key mixes a
secret kept in DATA_DIR with the password, so changing the password logs everyone out.
"""
import hashlib
import hmac
import secrets
import time
from pathlib import Path

COOKIE = "glm_session"
SESSION_SECONDS = 30 * 24 * 3600
# Reachable without logging in: the login page itself, its assets, icons and the Docker health check
PUBLIC_PATHS = {"/login", "/logout", "/favicon.ico", "/apple-touch-icon.png", "/api/health"}
PUBLIC_PREFIXES = ("/static/",)


class Auth:
    def __init__(self, username: str, password: str, data_dir: Path):
        if bool(username) != bool(password):
            raise ValueError("Set both AUTH_USERNAME and AUTH_PASSWORD to turn the login on, or neither to turn it off")
        self.username = username
        self.password = password
        self.enabled = bool(username)
        self._key = hmac.new(self._secret(data_dir), password.encode(), hashlib.sha256).digest() if self.enabled else b""

    @staticmethod
    def _secret(data_dir: Path) -> bytes:
        """Random secret kept in DATA_DIR, so sessions survive restarts."""
        path = data_dir / ".session_secret"
        if not path.exists():
            data_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(secrets.token_hex(32))
            path.chmod(0o600)
        return path.read_text().strip().encode()

    def check_credentials(self, username: str, password: str) -> bool:
        user_ok = hmac.compare_digest(username.encode(), self.username.encode())
        pass_ok = hmac.compare_digest(password.encode(), self.password.encode())
        return self.enabled and user_ok and pass_ok

    def _sign(self, expires: int) -> str:
        return hmac.new(self._key, f"{self.username}|{expires}".encode(), hashlib.sha256).hexdigest()

    def new_session(self) -> str:
        expires = int(time.time()) + SESSION_SECONDS
        return f"{expires}.{self._sign(expires)}"

    def valid_session(self, token: str | None) -> bool:
        if not token or "." not in token:
            return False
        expires, signature = token.split(".", 1)
        if not expires.isdigit() or int(expires) < time.time():
            return False
        return hmac.compare_digest(signature, self._sign(int(expires)))

    @staticmethod
    def is_public(path: str) -> bool:
        return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)
