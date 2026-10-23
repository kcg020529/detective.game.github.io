-- 같은 요청을 다시 보낼 때 처음 응답을 돌려주기 위한 로그
CREATE TABLE request_log (
    save_id BIGINT UNSIGNED NOT NULL,
    client_request_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    endpoint VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    response_json JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (save_id, client_request_id),
    CONSTRAINT fk_request_log_save FOREIGN KEY (save_id)
        REFERENCES saves (save_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
