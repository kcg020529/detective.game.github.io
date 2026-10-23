-- Location identifiers currently match the names used in data/ JSON sources.
CREATE TABLE locations (
    location_id VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    PRIMARY KEY (location_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO locations (location_id) VALUES
    ('중앙홀'), ('회의실'), ('기록실'), ('전력실'), ('통신실'), ('창고'), ('서버실');

CREATE TABLE game_record_locations (
    dataset VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    record_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    location_id VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    PRIMARY KEY (dataset, record_id, location_id),
    KEY ix_record_locations_lookup (location_id, dataset, record_id),
    CONSTRAINT fk_record_locations_record FOREIGN KEY (dataset, record_id)
        REFERENCES game_records (dataset, record_id) ON DELETE CASCADE,
    CONSTRAINT fk_record_locations_location FOREIGN KEY (location_id)
        REFERENCES locations (location_id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
