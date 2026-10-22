-- Per-user save slots. Apply after 002_users.sql.
CREATE TABLE saves (
    save_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    slot_no TINYINT UNSIGNED NOT NULL,
    role VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    day TINYINT UNSIGNED NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_played_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (save_id),
    UNIQUE KEY uq_saves_user_slot (user_id, slot_no),
    KEY ix_saves_user_last_played (user_id, last_played_at),
    CONSTRAINT fk_saves_user FOREIGN KEY (user_id)
        REFERENCES users (user_id) ON DELETE RESTRICT,
    CONSTRAINT ck_saves_slot CHECK (slot_no BETWEEN 1 AND 3),
    CONSTRAINT ck_saves_role CHECK (role IN ('prof', 'grad', 'std')),
    CONSTRAINT ck_saves_day CHECK (day BETWEEN 1 AND 6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
