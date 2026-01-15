-- =============================================================================
-- Config Control Plane Database Schema
-- =============================================================================
-- 
-- Stores configuration records with full lifecycle support:
-- - draft: Work in progress, modifiable
-- - proposed: Ready for review, read-only
-- - published: Production-ready, locked
-- - deprecated: Marked for removal
-- - archived: Historical reference
--
-- =============================================================================

-- Config records with full lifecycle support
CREATE TABLE IF NOT EXISTS config_records (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL CHECK(source_type IN ('object', 'handle', 'builtin', 'custom')),
    source_ref TEXT NOT NULL,
    fingerprint TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    
    -- Lifecycle
    state TEXT NOT NULL DEFAULT 'draft' CHECK(state IN ('draft', 'proposed', 'published', 'deprecated', 'archived')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL,
    published_at TIMESTAMP,
    published_by TEXT,
    
    -- Content
    config_json TEXT NOT NULL,  -- Full DataTypeConfig JSON
    extends_id TEXT REFERENCES config_records(id),
    overlays_json TEXT,
    
    -- Metadata
    object_type TEXT,
    ai_provider TEXT,
    confidence REAL DEFAULT 1.0,
    generation_time_ms REAL,
    
    -- Audit
    change_summary TEXT,
    change_author TEXT,
    
    -- Unique constraint on source_ref + fingerprint + version
    UNIQUE(source_ref, fingerprint, version)
);

-- Audit log for all changes
CREATE TABLE IF NOT EXISTS config_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id TEXT NOT NULL REFERENCES config_records(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    old_state TEXT,
    new_state TEXT,
    changed_by TEXT NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    diff_json TEXT,
    reason TEXT
);

-- User overrides for personalized config preferences
CREATE TABLE IF NOT EXISTS user_config_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    override_config_json TEXT NOT NULL,  -- Partial or full config override
    priority INTEGER DEFAULT 100,  -- Lower = higher priority
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1,
    UNIQUE(user_id, source_ref)
);

-- Config version history for diff visualization
CREATE TABLE IF NOT EXISTS config_version_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id TEXT NOT NULL REFERENCES config_records(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    config_json TEXT NOT NULL,
    snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(config_id, version)
);

-- Config test results for validation against real data
CREATE TABLE IF NOT EXISTS config_test_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id TEXT NOT NULL REFERENCES config_records(id) ON DELETE CASCADE,
    test_type TEXT NOT NULL,  -- 'schema', 'data', 'performance', 'integration'
    test_status TEXT NOT NULL,  -- 'passed', 'failed', 'warning'
    test_details_json TEXT,  -- Detailed test results
    tested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tested_by TEXT,
    execution_time_ms REAL
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_config_source ON config_records(source_type, source_ref);
CREATE INDEX IF NOT EXISTS idx_config_state ON config_records(state);
CREATE INDEX IF NOT EXISTS idx_config_fingerprint ON config_records(fingerprint);
CREATE INDEX IF NOT EXISTS idx_config_object_type ON config_records(object_type);
CREATE INDEX IF NOT EXISTS idx_config_extends ON config_records(extends_id);
CREATE INDEX IF NOT EXISTS idx_audit_config_id ON config_audit_log(config_id);
CREATE INDEX IF NOT EXISTS idx_audit_changed_at ON config_audit_log(changed_at);
CREATE INDEX IF NOT EXISTS idx_user_override_user ON user_config_overrides(user_id, source_ref);
CREATE INDEX IF NOT EXISTS idx_version_history_config ON config_version_history(config_id, version);
CREATE INDEX IF NOT EXISTS idx_test_results_config ON config_test_results(config_id, test_type);