# Usage Patterns

## Automatic Handoff Capture

```bash
# Handoff is captured automatically before /compact
# Just run /compact normally - no extra steps needed
```

## Manual Handoff Generation (Debugging)

```bash
# For debugging or manual operations:
python -m scripts.cli list       # Show handoff details
python -m scripts.cli restore    # Show restore status
python -m scripts.cli debug      # Debug mode (validation, checksum, decisions)
python -m scripts.cli cleanup    # Clean up old handoffs (dry-run)
```

## Session Continuity Workflow

### Before Compact/Handover
1. `/handoff detailed` - Document current work
2. Log critical decisions with ADRs
3. Define next session objectives
4. `/handoff quality` - Assess completeness

### After Compact/Handover
1. `/handoff load` - Restore previous context
2. Review decisions for continuity
3. Check quality score
4. Continue with prioritized objectives
