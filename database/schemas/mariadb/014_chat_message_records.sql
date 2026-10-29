-- 허용된 요약이나 본문이 전달된 AI 메시지만 연결한다.
CREATE TABLE chat_message_records (
    message_id BIGINT UNSIGNED NOT NULL,
    dataset VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    record_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    PRIMARY KEY (message_id, dataset, record_id),
    CONSTRAINT fk_chat_message_records_message FOREIGN KEY (message_id)
        REFERENCES chat_messages (message_id) ON DELETE CASCADE,
    CONSTRAINT fk_chat_message_records_record FOREIGN KEY (dataset, record_id)
        REFERENCES game_records (dataset, record_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
