-- Paused Sessions and Intervention Management
-- ============================================
-- Stores session state when paused due to blockers

-- Table for paused sessions
CREATE TABLE IF NOT EXISTS paused_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Pause information
    paused_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pause_reason TEXT NOT NULL,
    pause_type VARCHAR(50) NOT NULL, -- 'retry_limit', 'critical_error', 'manual', 'timeout'

    -- Current state when paused
    current_task_id INTEGER REFERENCES tasks(id),
    current_task_description TEXT,
    message_count INTEGER,

    -- Blocker details
    blocker_info JSONB NOT NULL DEFAULT '{}',
    retry_stats JSONB NOT NULL DEFAULT '{}',
    error_messages TEXT[],

    -- Resolution tracking
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    resolution_notes TEXT,
    resolved_by VARCHAR(255),

    -- Resume information
    can_auto_resume BOOLEAN DEFAULT FALSE,
    resume_prompt TEXT, -- Custom prompt to use when resuming
    resume_context JSONB DEFAULT '{}', -- Additional context for resume

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_active_pause_per_session UNIQUE (session_id, resolved)
);

-- Table for intervention actions taken
CREATE TABLE IF NOT EXISTS intervention_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paused_session_id UUID NOT NULL REFERENCES paused_sessions(id) ON DELETE CASCADE,

    -- Action details
    action_type VARCHAR(50) NOT NULL, -- 'notification_sent', 'auto_recovery', 'manual_fix', 'resumed'
    action_status VARCHAR(20) NOT NULL, -- 'pending', 'success', 'failed'
    action_details JSONB NOT NULL DEFAULT '{}',

    -- Timing
    initiated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    -- Results
    result_message TEXT,
    error_message TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Table for notification preferences per project
CREATE TABLE IF NOT EXISTS notification_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Notification channels
    webhook_enabled BOOLEAN DEFAULT FALSE,
    webhook_url TEXT,

    email_enabled BOOLEAN DEFAULT FALSE,
    email_addresses TEXT[],

    sms_enabled BOOLEAN DEFAULT FALSE,
    sms_numbers TEXT[],

    -- Notification triggers
    notify_on_retry_limit BOOLEAN DEFAULT TRUE,
    notify_on_critical_error BOOLEAN DEFAULT TRUE,
    notify_on_timeout BOOLEAN DEFAULT TRUE,
    notify_on_manual_pause BOOLEAN DEFAULT FALSE,

    -- Rate limiting
    min_notification_interval INTEGER DEFAULT 300, -- Minimum seconds between notifications
    last_notification_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_preferences_per_project UNIQUE (project_id)
);

-- Indexes for performance
CREATE INDEX idx_paused_sessions_project ON paused_sessions(project_id);
CREATE INDEX idx_paused_sessions_resolved ON paused_sessions(resolved);
CREATE INDEX idx_paused_sessions_paused_at ON paused_sessions(paused_at DESC);
CREATE INDEX idx_intervention_actions_paused_session ON intervention_actions(paused_session_id);
CREATE INDEX idx_intervention_actions_initiated_at ON intervention_actions(initiated_at DESC);

-- Views for dashboard
CREATE OR REPLACE VIEW v_active_interventions AS
SELECT
    ps.id,
    ps.session_id,
    ps.project_id,
    p.name as project_name,
    ps.paused_at,
    ps.pause_reason,
    ps.pause_type,
    ps.current_task_description,
    ps.blocker_info,
    ps.retry_stats,
    ps.can_auto_resume,
    COALESCE(
        (SELECT COUNT(*)
         FROM intervention_actions ia
         WHERE ia.paused_session_id = ps.id
         AND ia.action_type = 'notification_sent'
         AND ia.action_status = 'success'),
        0
    ) as notifications_sent,
    NOW() - ps.paused_at as time_paused
FROM paused_sessions ps
JOIN projects p ON ps.project_id = p.id
WHERE ps.resolved = FALSE
ORDER BY ps.paused_at DESC;

CREATE OR REPLACE VIEW v_intervention_history AS
SELECT
    ps.id,
    ps.project_id,
    p.name as project_name,
    ps.paused_at,
    ps.pause_type,
    ps.resolved_at,
    ps.resolution_notes,
    ps.resolved_by,
    ps.resolved_at - ps.paused_at as resolution_time,
    array_agg(
        DISTINCT jsonb_build_object(
            'type', ia.action_type,
            'status', ia.action_status,
            'initiated_at', ia.initiated_at
        )
    ) as actions_taken
FROM paused_sessions ps
JOIN projects p ON ps.project_id = p.id
LEFT JOIN intervention_actions ia ON ps.id = ia.paused_session_id
WHERE ps.resolved = TRUE
GROUP BY ps.id, p.id, p.name
ORDER BY ps.resolved_at DESC;

-- Function to pause a session
CREATE OR REPLACE FUNCTION pause_session(
    p_session_id UUID,
    p_project_id UUID,
    p_reason TEXT,
    p_pause_type VARCHAR(50),
    p_blocker_info JSONB DEFAULT '{}',
    p_retry_stats JSONB DEFAULT '{}',
    p_current_task_id INTEGER DEFAULT NULL,
    p_current_task_description TEXT DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
    v_paused_session_id UUID;
BEGIN
    INSERT INTO paused_sessions (
        session_id,
        project_id,
        pause_reason,
        pause_type,
        blocker_info,
        retry_stats,
        current_task_id,
        current_task_description
    ) VALUES (
        p_session_id,
        p_project_id,
        p_reason,
        p_pause_type,
        p_blocker_info,
        p_retry_stats,
        p_current_task_id,
        p_current_task_description
    )
    RETURNING id INTO v_paused_session_id;

    -- Update session status
    UPDATE sessions
    SET status = 'paused',
        updated_at = NOW()
    WHERE id = p_session_id;

    RETURN v_paused_session_id;
END;
$$ LANGUAGE plpgsql;

-- Function to resume a session
CREATE OR REPLACE FUNCTION resume_session(
    p_paused_session_id UUID,
    p_resolved_by VARCHAR(255) DEFAULT 'system',
    p_resolution_notes TEXT DEFAULT NULL
) RETURNS BOOLEAN AS $$
BEGIN
    -- Mark as resolved
    UPDATE paused_sessions
    SET resolved = TRUE,
        resolved_at = NOW(),
        resolved_by = p_resolved_by,
        resolution_notes = p_resolution_notes,
        updated_at = NOW()
    WHERE id = p_paused_session_id
    AND resolved = FALSE;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    -- Update session status
    UPDATE sessions
    SET status = 'resumed',
        updated_at = NOW()
    WHERE id = (
        SELECT session_id
        FROM paused_sessions
        WHERE id = p_paused_session_id
    );

    -- Log the resume action
    INSERT INTO intervention_actions (
        paused_session_id,
        action_type,
        action_status,
        action_details,
        completed_at
    ) VALUES (
        p_paused_session_id,
        'resumed',
        'success',
        jsonb_build_object('resolved_by', p_resolved_by),
        NOW()
    );

    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;