-- Server-side login sessions. Store only a SHA-256 hash of the random cookie.
CREATE TABLE auth_sessions (
    session_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    expires_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_hash),
    KEY ix_auth_sessions_user (user_id),
    KEY ix_auth_sessions_expires (expires_at),
    CONSTRAINT fk_auth_sessions_user FOREIGN KEY (user_id)
        REFERENCES users (user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
