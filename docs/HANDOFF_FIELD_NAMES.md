# Handoff Hook Input Fields

This document records the hook input fields used by the current Handoff V2 implementation.

## PreCompact

Required fields:

| Field | Type | Notes |
|------|------|------|
| `session_id` | `string` | Source Claude session id |
| `transcript_path` | `string` | Transcript JSONL path |
| `cwd` | `string` | Current working directory |
| `hook_event_name` | `string` | Expected: `PreCompact` |
| `trigger` | `string` | Example: `auto`, `manual` |

Optional fields:

| Field | Type | Notes |
|------|------|------|
| `terminal_id` | `string` | Explicit terminal identity override |
| `test_mode` | `bool` | Accepted by validator; not used on the V2 core path |

## SessionStart

Required fields:

| Field | Type | Notes |
|------|------|------|
| `session_id` | `string` | New Claude session id |
| `cwd` | `string` | Current working directory |
| `hook_event_name` | `string` | Expected: `SessionStart` |
| `trigger` | `string` | Used when normalizing post-compact restore source |

Optional fields:

| Field | Type | Notes |
|------|------|------|
| `terminal_id` | `string` | Explicit terminal identity override |
| `source` | `string` | Preferred post-compact source indicator |
| `transcript_path` | `string` | Optional project-root hint |

## Conventions

- Claude Code hook fields are snake_case.
- Do not rely on camelCase fields like `sessionId` or `transcriptPath`.
- `SessionStart` restore is normalized to `compact` only for known compact-like values such as:
  - `compact`
  - `post_compact`
  - `post-compact`
  - `resume_after_compact`
  - `compaction`

If no compact-like source is present, the V2 restore hook does not automatically inject task context.
