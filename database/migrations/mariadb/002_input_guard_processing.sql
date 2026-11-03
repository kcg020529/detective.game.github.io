-- Allow both historical detection-only events (high_risk=true) and the new
-- enforced events (high_risk=false). The application validates new writes.
ALTER TABLE audit_events
    DROP CONSTRAINT ck_audit_events_input_level,
    ADD CONSTRAINT ck_audit_events_input_level CHECK (
        event_type <> 'input_guard_alert' OR
        (level IN ('warn', 'high_risk') AND score IN (50, 90))
    );
