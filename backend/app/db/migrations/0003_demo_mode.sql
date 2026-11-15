-- 0003_demo_mode.sql
-- Adds strict backend demo-vs-production isolation flags across astronauts, missions,
-- SOS alerts, field observations, and mission events.

ALTER TABLE astronauts ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0;
ALTER TABLE missions ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0;
ALTER TABLE sos_events ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0;
ALTER TABLE field_observations ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0;
ALTER TABLE mission_events ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_astronauts_is_demo ON astronauts(is_demo);
CREATE INDEX IF NOT EXISTS idx_missions_is_demo ON missions(is_demo);

