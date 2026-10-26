-- Existing databases only. Back up and pause policy writes before applying.
-- The old basic_metadata exposes fewer fields than metadata. Do not promote it.
-- Review the count below, then re-import reviewed records with the role policy.
SELECT dataset, COUNT(*) AS legacy_permission_rows
FROM document_permissions
WHERE disclosure_level = 'basic_metadata'
GROUP BY dataset;

START TRANSACTION;
UPDATE document_permissions
SET disclosure_level = 'deny'
WHERE disclosure_level = 'basic_metadata';
COMMIT;

-- MariaDB DDL commits implicitly. Keep DROP/ADD in one ALTER statement.
-- Re-running is safe: the same named constraint is replaced again.
ALTER TABLE document_permissions
    DROP CONSTRAINT ck_document_permissions_level,
    ADD CONSTRAINT ck_document_permissions_level CHECK (
        disclosure_level IN ('full', 'summary', 'metadata', 'deny')
    );
