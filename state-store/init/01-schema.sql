-- Cloud Seed MCP — State Store Schema
-- Initialised automatically by postgres:16-alpine on first boot.

-- =============================================================
-- Tables
-- =============================================================

-- Tracked GCP projects
CREATE TABLE projects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gcp_project_id  TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Infrastructure resources synced from Terraform state
CREATE TABLE resources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID REFERENCES projects(id),
    resource_type   TEXT NOT NULL,
    resource_name   TEXT NOT NULL,
    address         TEXT NOT NULL,
    state_json      JSONB NOT NULL,
    last_synced_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE(project_id, address)
);

-- Custom tools generated and managed by Tool Forge
CREATE TABLE tool_registry (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT UNIQUE NOT NULL,
    version         TEXT NOT NULL,
    description     TEXT,
    schema_json     JSONB NOT NULL,
    code_hash       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'staging'
                        CHECK (status IN ('staging', 'active', 'deprecated')),
    created_at      TIMESTAMPTZ DEFAULT now(),
    promoted_at     TIMESTAMPTZ
);

-- Synchronisation history (terraform / github / gcloud)
CREATE TABLE sync_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          TEXT NOT NULL
                        CHECK (source IN ('terraform', 'github', 'gcloud')),
    project_id      UUID REFERENCES projects(id),
    started_at      TIMESTAMPTZ DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running', 'success', 'failed')),
    details         JSONB DEFAULT '{}'
);

-- Audit trail for every action executed by the system
CREATE TABLE action_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action_type     TEXT NOT NULL,
    classification  TEXT NOT NULL
                        CHECK (classification IN ('green', 'yellow', 'red')),
    project_id      UUID REFERENCES projects(id),
    tool_name       TEXT NOT NULL,
    request_json    JSONB,
    response_json   JSONB,
    approved_by     TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- =============================================================
-- Indexes
-- =============================================================

-- resources
CREATE INDEX idx_resources_project_id ON resources(project_id);
CREATE INDEX idx_resources_type       ON resources(resource_type);

-- tool_registry
CREATE INDEX idx_tool_registry_status ON tool_registry(status);

-- sync_log
CREATE INDEX idx_sync_log_project_id ON sync_log(project_id);
CREATE INDEX idx_sync_log_source     ON sync_log(source);
CREATE INDEX idx_sync_log_status     ON sync_log(status);

-- action_log
CREATE INDEX idx_action_log_project_id     ON action_log(project_id);
CREATE INDEX idx_action_log_classification ON action_log(classification);
CREATE INDEX idx_action_log_created_at     ON action_log(created_at);
CREATE INDEX idx_action_log_tool_name      ON action_log(tool_name);
