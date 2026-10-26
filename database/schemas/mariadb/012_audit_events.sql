-- H01: metadata-only security audit events. Never store prompts, answers, or secrets.
-- The first supported event type is input_guard_alert; other producers need an
-- agreed event contract before writing to this table.
CREATE TABLE IF NOT EXISTS audit_events (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    occurred_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    request_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    event_type VARCHAR(40) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    level VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    score TINYINT UNSIGNED NOT NULL,
    signals_json JSON NOT NULL,
    continue_processing BOOLEAN NOT NULL,
    user_id BIGINT UNSIGNED NULL,
    save_id BIGINT UNSIGNED NULL,
    role VARCHAR(8) CHARACTER SET ascii COLLATE ascii_bin NULL,
    character_id VARCHAR(8) CHARACTER SET ascii COLLATE ascii_bin NULL,
    PRIMARY KEY (event_id),
    KEY ix_audit_events_time (occurred_at, event_id),
    KEY ix_audit_events_type_time (event_type, occurred_at),
    KEY ix_audit_events_level_time (level, occurred_at),
    KEY ix_audit_events_request (request_id),
    CONSTRAINT fk_audit_events_user FOREIGN KEY (user_id)
        REFERENCES users (user_id) ON DELETE SET NULL,
    CONSTRAINT fk_audit_events_save FOREIGN KEY (save_id)
        REFERENCES saves (save_id) ON DELETE SET NULL,
    CONSTRAINT ck_audit_events_input_level CHECK (
        event_type <> 'input_guard_alert' OR
        (level IN ('warn', 'high_risk') AND score IN (50, 90) AND continue_processing = 1)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
