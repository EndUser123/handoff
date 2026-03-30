# Retention Policy & Auto-Cleanup

## Retention Policy

Handoff documents are retained for **90 days** by default (configurable via `HANDOFF_RETENTION_DAYS` env var).

After 90 days, handoffs are candidates for cleanup because:
- Context is stale for session-bridging purposes
- Relevant decisions should be captured in CKS/patterns
- Storage efficiency for long-running projects

## Auto-Cleanup

```bash
# Manual cleanup (for debugging):
python -m scripts.cli cleanup --dry-run

# Execute cleanup
python -m scripts.cli cleanup

# Custom retention period
export HANDOFF_RETENTION_DAYS=30
```

**Auto-cleanup behavior**:
- Handover documents older than 90 days are candidates for deletion
- Dry-run mode shows what would be deleted without actually deleting
- Use `--force` to actually delete files
- Customize retention via `HANDOFF_RETENTION_DAYS` environment variable

**Rationale**: Handover documents are session-bridging artifacts, not permanent records. After 90 days, context is stale and relevant decisions should be captured in CKS/patterns.

## Data Storage

| Data | Path |
|------|------|
| Session State | `__csf/.staging/claude_session.json` |
| Work Context | `__csf/.staging/work_context.json` |
| Handover Documents | `__csf/.staging/handovers/` |
| Quality Metrics | `__csf/.staging/quality_metrics.json` |
