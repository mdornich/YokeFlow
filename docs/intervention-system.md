# YokeFlow Intervention System

## Overview

The YokeFlow Intervention System (Phase 2) prevents infinite retry loops, detects critical infrastructure errors, and sends notifications when sessions get stuck. This system was developed in response to Session 11's catastrophic failure where the agent spent 472 seconds in an infinite retry loop.

## Features

### 1. Retry Tracking
- Monitors repeated command executions
- Blocks after configurable retry limit (default: 3 attempts)
- Detects rapid repetition patterns

### 2. Critical Error Detection
- Identifies infrastructure blockers:
  - Prisma schema validation errors
  - Missing dependencies (Redis, Prisma, etc.)
  - Database connection failures
  - Port conflicts
  - Module not found errors
- Immediately flags errors requiring human intervention

### 3. Webhook Notifications
- Sends alerts when intervention is needed
- Supports Slack, Discord, and generic webhooks
- Includes retry statistics and error details

### 4. Automatic Blocker Documentation
- Creates structured entries in `claude-progress.md`
- Records attempted solutions and root causes
- Provides clear action items for resolution

## Configuration

### Enable in `.yokeflow.yaml`

```yaml
intervention:
  enabled: true
  max_retries: 3
  error_rate_threshold: 0.15
  session_duration_limit: 600
  detect_infrastructure_errors: true
```

### Set Webhook URL

#### Option 1: Configuration File
```yaml
intervention:
  webhook_url: "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX"
```

#### Option 2: Environment Variable
```bash
export YOKEFLOW_WEBHOOK_URL="https://hooks.slack.com/services/..."
```

### Webhook Setup

#### Slack
1. Go to https://api.slack.com/apps
2. Create a new app or select existing
3. Add "Incoming Webhooks" feature
4. Create webhook for your channel
5. Copy webhook URL to configuration

#### Discord
1. Open Discord channel settings
2. Go to Integrations → Webhooks
3. Create new webhook
4. Copy webhook URL to configuration

## How It Works

### During Sessions

1. **Every tool call is tracked**
   - Command signature is hashed
   - Retry count is incremented for duplicates

2. **Errors are analyzed**
   - Checked against critical patterns
   - Infrastructure issues flagged immediately

3. **When limits are exceeded**
   - Session is halted
   - Blocker is documented in `claude-progress.md`
   - Webhook notification is sent
   - Session ends with error status

### Blocker Format

When a blocker is detected, it's documented as:

```markdown
## BLOCKER - Session [ID] - [Timestamp]

**Task:** 237 - Implement RBAC system
**Issue:** Command attempted 4 times: npm start
**Root Cause:** Automated retry limit exceeded

**Retry Statistics:**
{
  "total_retries": 10,
  "max_retries_on_single_command": 4,
  "unique_errors": 3
}

**Requires:**
- [ ] Human intervention to resolve infrastructure issue
- [ ] Review logs in `logs/` directory
- [ ] Fix root cause before resuming

**Impact:** Session halted to prevent infinite loops
```

## Notification Format

Webhook notifications include:

```
🚨 YokeFlow Session Blocked

Project: flowforge
Session: abc-123-def
Time: 2024-01-01 12:00:00

Blocker Type: prisma_schema_error
Error: Prisma schema validation failed...

Retry Statistics:
• Total retries: 10
• Max retries on single command: 4
• Unique errors: 3

Action Required: Manual intervention needed

View logs: generations/flowforge/logs/
```

## Testing

Run the test suite to verify configuration:

```bash
python tests/test_intervention.py
```

This tests:
- Retry tracking
- Blocker detection
- Notification sending (if webhook configured)

## Benefits

### Without Intervention (Session 11)
- 472 seconds wasted in retry loop
- 14.3% error rate
- 10+ attempts at same failing command
- No notification of issues
- Resources wasted

### With Intervention
- Maximum 3 attempts before blocking
- Immediate notification on critical errors
- Clear documentation of blockers
- Human alerted for resolution
- Resources preserved

## Troubleshooting

### Notifications Not Sending
1. Check webhook URL is correct
2. Verify network connectivity
3. Check webhook service is active
4. Review logs for notification errors

### Too Many False Positives
1. Increase `max_retries` setting
2. Adjust `error_rate_threshold`
3. Review blocked patterns in logs

### Not Catching Errors
1. Ensure `enabled: true` in config
2. Check error patterns match
3. Review `detect_infrastructure_errors` setting

## Future Enhancements (Phase 3)

- Pause/resume capability
- Email and SMS notifications
- Web UI for intervention management
- Auto-recovery actions
- Machine learning for pattern detection

## Related Documentation

- [Session 11 Failure Analysis](../analysis/session-11-failure-analysis-report.md)
- [Coding Prompt Updates](../prompts/coding_prompt_docker.md)
- [Configuration Guide](configuration.md)