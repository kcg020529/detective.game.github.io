-- Save마다 최종 지목은 한 번만 저장한다.
CREATE TABLE accusations (
    save_id BIGINT UNSIGNED NOT NULL,
    ai_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    is_correct BOOLEAN NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (save_id),
    CONSTRAINT fk_accusations_save FOREIGN KEY (save_id)
        REFERENCES saves (save_id) ON DELETE CASCADE,
    CONSTRAINT ck_accusations_ai CHECK (ai_id IN ('YB-1', 'YB-2', 'YB-3', 'YB-4', 'YB-5', 'YB-6'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
