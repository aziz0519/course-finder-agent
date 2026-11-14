-- Initial M2 local reading registry. Derived binaries stay outside SQLite.
-- Future schema changes must be separate numbered migrations.
CREATE TABLE IF NOT EXISTS reading_versions (
    document_id TEXT NOT NULL,
    version TEXT NOT NULL,
    course_id TEXT NOT NULL,
    title TEXT NOT NULL,
    artifact_dir TEXT NOT NULL,
    parsed_json TEXT NOT NULL,
    report_json TEXT NOT NULL,
    PRIMARY KEY(document_id, version)
);
CREATE INDEX IF NOT EXISTS reading_versions_course
    ON reading_versions(course_id, document_id, version);
CREATE TABLE IF NOT EXISTS active_readings (
    document_id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    FOREIGN KEY(document_id, version)
        REFERENCES reading_versions(document_id, version)
);
PRAGMA user_version = 1;
