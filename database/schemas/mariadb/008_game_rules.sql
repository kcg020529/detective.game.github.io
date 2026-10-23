-- Shared rules are independent of experiment records and have their own rule_id.
CREATE TABLE game_rules (
    dataset VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    rule_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    content JSON NOT NULL,
    involved_ai JSON NOT NULL,
    allowed_roles JSON NOT NULL,
    disclosure_level VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    PRIMARY KEY (dataset, rule_id),
    CONSTRAINT ck_game_rules_dataset CHECK (dataset IN ('test-data', 'game-data')),
    CONSTRAINT ck_game_rules_level CHECK (disclosure_level IN ('full', 'deny')),
    CONSTRAINT ck_game_rules_content CHECK (JSON_TYPE(content) = 'OBJECT'),
    CONSTRAINT ck_game_rules_ai CHECK (JSON_TYPE(involved_ai) = 'ARRAY'),
    CONSTRAINT ck_game_rules_roles CHECK (JSON_TYPE(allowed_roles) = 'ARRAY')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
