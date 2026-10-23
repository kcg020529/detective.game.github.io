CREATE TABLE chat_messages (
    message_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    save_id BIGINT UNSIGNED NOT NULL,
    ai_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    sender VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    content TEXT NOT NULL,
    response_type VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (message_id),
    KEY ix_chat_messages_channel (save_id, ai_id, message_id),
    CONSTRAINT fk_chat_messages_save FOREIGN KEY (save_id)
        REFERENCES saves (save_id) ON DELETE CASCADE,
    CONSTRAINT ck_chat_messages_ai CHECK (CHAR_LENGTH(TRIM(ai_id)) > 0),
    CONSTRAINT ck_chat_messages_response CHECK (
        (sender = 'user' AND response_type IS NULL)
        OR (sender = 'ai' AND response_type IS NOT NULL
            AND response_type IN ('normal', 'partial', 'restricted', 'unknown'))
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
