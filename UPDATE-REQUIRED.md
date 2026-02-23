# Database Updates Required (v1.3.0 → v1.4.0)

⚠️ **Action Required for Existing Installations**

If you're upgrading from v1.3.0 or earlier, you need to apply database schema updates for the production hardening features.

## Quick Update (Recommended)

Run these commands to apply all schema updates in order:

**Via Docker:**
```bash
# Apply intervention system tables (v1.4.0)
docker exec -i yokeflow_postgres psql -U agent -d yokeflow < schema/postgresql/011_paused_sessions.sql

# Apply session checkpointing tables (v1.4.0)
docker exec -i yokeflow_postgres psql -U agent -d yokeflow < schema/postgresql/012_session_checkpoints.sql
```

**Direct PostgreSQL:**
```bash
# Apply intervention system tables (v1.4.0)
psql -U agent -d yokeflow < schema/postgresql/011_paused_sessions.sql

# Apply session checkpointing tables (v1.4.0)
psql -U agent -d yokeflow < schema/postgresql/012_session_checkpoints.sql
```

## What's Changed?

### 1. Intervention System (P0 Critical)
**File:** `schema/postgresql/011_paused_sessions.sql`

**New Tables:**
- `paused_sessions` - Tracks paused sessions with reasons and metadata
- `intervention_actions` - Audit trail of intervention actions
- `notification_preferences` - User notification settings for interventions

**New Views:**
- `v_active_interventions` - Shows currently paused sessions
- `v_intervention_history` - Complete intervention audit trail

**New Functions:**
- `pause_session()` - Pause a session with reason
- `resume_session()` - Resume a paused session

**Impact if not applied:**
- ❌ Intervention system won't work
- ❌ Sessions can't be paused/resumed
- ❌ No audit trail for interventions

### 2. Session Checkpointing (P0 Critical)
**File:** `schema/postgresql/012_session_checkpoints.sql`

**New Tables:**
- `session_checkpoints` - Stores complete session state at key points
- `checkpoint_recoveries` - Tracks recovery attempts from checkpoints

**New Views:**
- `v_latest_checkpoints` - Most recent checkpoint per session
- `v_resumable_checkpoints` - Valid checkpoints for recovery
- `v_checkpoint_recovery_history` - Recovery attempt history

**New Functions:**
- `create_checkpoint()` - Create a new checkpoint
- `start_checkpoint_recovery()` - Begin recovery from checkpoint
- `complete_checkpoint_recovery()` - Mark recovery as successful

**Impact if not applied:**
- ❌ No session checkpointing capability
- ❌ Can't resume from failures
- ❌ No session state preservation

## Verification

After applying updates, verify with:

```bash
# Check that session_quality_checks no longer has check_type
docker exec yokeflow_postgres psql -U agent -d yokeflow -c "\d session_quality_checks"

# Check that prompt_proposals has metadata column
docker exec yokeflow_postgres psql -U agent -d yokeflow -c "\d prompt_proposals" | grep metadata
```

You should see:
- ✅ `session_quality_checks` has 13 columns (no `check_type`, `review_text`, etc.)
- ✅ `prompt_proposals` has `metadata` column

## Fresh Installation?

If you're doing a **fresh installation** (not upgrading), you don't need these migrations.
The main schema file (`schema/postgresql/schema.sql`) already includes all updates.

## Questions?

If you encounter issues, check the migration scripts themselves - they use `IF EXISTS`/`IF NOT EXISTS`
so they're safe to run multiple times and won't fail if changes are already applied.

---

**Note:** These migrations are safe and idempotent. Running them multiple times won't cause errors.
