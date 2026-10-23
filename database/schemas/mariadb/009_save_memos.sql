-- Save별 플레이어 메모 1개 (최대 5000자)
CREATE TABLE save_memos (
    save_id BIGINT UNSIGNED NOT NULL,
    memo TEXT NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (save_id),
    CONSTRAINT fk_save_memos_save FOREIGN KEY (save_id)
        REFERENCES saves (save_id) ON DELETE CASCADE,
    CONSTRAINT ck_save_memos_length CHECK (CHAR_LENGTH(memo) <= 5000)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
