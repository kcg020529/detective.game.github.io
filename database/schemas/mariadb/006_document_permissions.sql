-- Authoritative disclosure policy. No row means deny.
-- Legacy game_record_allowed_roles must not be used as an authorization fallback.
CREATE TABLE document_permissions (
    dataset VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    record_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    role VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    disclosure_level VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    PRIMARY KEY (dataset, record_id, role),
    KEY ix_document_permissions_role (dataset, role, disclosure_level),
    CONSTRAINT fk_document_permissions_record FOREIGN KEY (dataset, record_id)
        REFERENCES game_records (dataset, record_id) ON DELETE CASCADE,
    CONSTRAINT ck_document_permissions_role CHECK (role IN ('prof', 'grad', 'std')),
    CONSTRAINT ck_document_permissions_level CHECK (
        disclosure_level IN ('full', 'summary', 'metadata', 'deny')
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
