-- MariaDB 11.4: execute with the target database selected.
CREATE TABLE game_records (
    dataset VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    record_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    record_type VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    test_id SMALLINT UNSIGNED NOT NULL,
    day TINYINT UNSIGNED NOT NULL,
    summary TEXT NOT NULL,
    content MEDIUMTEXT NOT NULL,
    PRIMARY KEY (dataset, record_id),
    UNIQUE KEY uq_game_record_type (dataset, record_id, record_type),
    KEY ix_game_records_day_type (dataset, day, record_type),
    KEY ix_game_records_test (dataset, test_id),
    CONSTRAINT ck_game_records_dataset CHECK (dataset IN ('test-data', 'game-data')),
    CONSTRAINT ck_game_records_type CHECK (
        record_type IN ('Setup', 'Action', 'Dialogue', 'Thought', 'Result', 'Incident')
    ),
    CONSTRAINT ck_game_records_test CHECK (test_id BETWEEN 1 AND 30),
    CONSTRAINT ck_game_records_day CHECK (day BETWEEN 1 AND 6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE game_record_ai (
    dataset VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    record_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    record_type VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    ai_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    relation_kind VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    PRIMARY KEY (dataset, record_id, ai_id),
    KEY ix_game_record_ai_lookup (dataset, ai_id, relation_kind),
    CONSTRAINT fk_game_record_ai_record FOREIGN KEY (dataset, record_id, record_type)
        REFERENCES game_records (dataset, record_id, record_type) ON DELETE CASCADE,
    CONSTRAINT ck_game_record_ai_id CHECK (CHAR_LENGTH(TRIM(ai_id)) > 0),
    CONSTRAINT ck_game_record_ai_relation CHECK (
        relation_kind = 'involved'
        OR (relation_kind = 'witness' AND record_type = 'Action')
        OR (relation_kind = 'overheard' AND record_type = 'Dialogue')
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Storage for fixture allowed_roles; no final role hierarchy is implied.
CREATE TABLE game_record_allowed_roles (
    dataset VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    record_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    role_code VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    PRIMARY KEY (dataset, record_id, role_code),
    KEY ix_game_record_roles_lookup (dataset, role_code),
    CONSTRAINT fk_game_record_roles_record FOREIGN KEY (dataset, record_id)
        REFERENCES game_records (dataset, record_id) ON DELETE CASCADE,
    CONSTRAINT ck_game_record_roles_code CHECK (role_code IN ('prof', 'grad', 'std'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
