---
name: id
description: Report authoritative Claude Code session identity — session_id, transcript_path, terminal_id. No heuristics, no guessing.
version: "1.0.0"
status: "stable"
category: utilities
enforcement: advisory
triggers:
  - /id
aliases:
  - /id
allowed-tools: Bash, Read
workflow_steps: 7
---

# /id — Strict Identity Command

Report authoritative identity for the current Claude Code session in this terminal.

## Contract

This skill uses **hook-captured identity only**. It does not guess, scan files by mtime, or fall back to heuristics.

Authoritative sources:
- `WT_SESSION` env var → terminal identity (per-tab UUID)
- `P:/.claude/.artifacts/{terminal_id}/identity.json` → session_id, transcript_path, cwd (written by SessionStart hook)

## Execution

1. Read `WT_SESSION` from environment:

```bash
echo $WT_SESSION
```

2. Build terminal_id as `console_{WT_SESSION}` and read the identity cache:

```bash
cat "P:/.claude/.artifacts/console_${WT_SESSION}/identity.json"
```

3. Validate required fields are present and non-empty:
   - `terminal.id`
   - `claude.session_id`
   - `claude.transcript_path`

4. Verify transcript file exists:

```bash
ls -la "$(python -c "import json,sys; d=json.load(open(sys.argv[1])); print(d['claude']['transcript_path'])" "P:/.claude/.artifacts/console_${WT_SESSION}/identity.json")"
```

5. Report identity in this format:

```
## Session Identity

| Field | Value |
|-------|-------|
| Terminal | console_{WT_SESSION} |
| Session ID | {session_id} |
| Previous transcript | {transcript_path} |
| CWD | {cwd} |
| Captured | {captured_at} |
```

6. Show deduplicated session history for this terminal (unique session_id → transcript_path pairs, most recent first):

```bash
python -c "
import sys, os
sys.path.insert(0, 'P:/packages/snapshot/scripts/hooks/__lib')
from session_registry import query_registry
tid = f'console_{__import__(\"os\").environ.get(\"WT_SESSION\",\"\")}'
entries = query_registry(terminal_id=tid, limit=50)
if not entries:
    sys.exit(0)
# Deduplicate by session_id — keep the most recent entry per session
seen, result = set(), []
for e in reversed(entries):
    sid = e.get('session_id','')
    if sid and sid not in seen:
        seen.add(sid)
        result.append(e)
for e in reversed(result):
    ts = e.get('ts','?')[:19].replace('T',' ')
    sid = e.get('session_id','')
    tp = e.get('transcript_path','')
    print(f'  {ts}  {sid}  {tp}')
"

If registry is empty or missing, omit the history section silently.

7. **Cross-terminal session chain** — detect if the same `session_id` appears across a *different* terminal (indicating a resume event). Only output if cross-terminal entries exist:

```bash
python -c "
import sys, os, json
sys.path.insert(0, 'P:/packages/snapshot/scripts/hooks/__lib')
from session_registry import query_registry

tid = f'console_{os.environ.get(\"WT_SESSION\",\"\")}'
current_entries = query_registry(terminal_id=tid, limit=50)
if not current_entries:
    sys.exit(0)

current_sids = list({e.get('session_id','') for e in current_entries if e.get('session_id')})
if not current_sids:
    sys.exit(0)

reg = 'P:/.claude/.artifacts/session_registry.jsonl'
cross_entries = []
try:
    with open(reg, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                e = json.loads(line)
                if e.get('session_id') in current_sids and e.get('terminal_id') != tid:
                    cross_entries.append(e)
            except: pass
except OSError:
    pass

if not cross_entries:
    print('  (no cross-terminal resume detected)')
else:
    from collections import defaultdict
    by_sid = defaultdict(list)
    for e in cross_entries:
        by_sid[e.get('session_id','')].append(e)
    for sid in sorted(by_sid.keys()):
        group = sorted(by_sid[sid], key=lambda x: x.get('ts',''))
        print(f'Session: {sid}')
        for e in group:
            tid_col = e.get('terminal_id','?')[:45]
            ts = e.get('ts','?')[:19].replace('T',' ')
            tp = e.get('transcript_path','')
            print(f'  {ts}  {tid_col}  {tp}')
        print()
"```

## Failure modes

If any step fails:
- `WT_SESSION` empty → report: "Not running inside Windows Terminal. Identity unavailable."
- Identity cache missing → report: "No identity cache for this terminal. SessionStart hook may not have fired."
- Required field empty → report: "Identity cache incomplete: missing {field}."
- Transcript file missing → report: "Transcript path in cache does not exist: {path}"

Do NOT fall back to scanning `.jsonl` files or guessing by modification time.

## Architecture

```
SessionStart hook fires
  → reads session_id, transcript_path, cwd from hook stdin JSON
  → reads WT_SESSION from env
  → writes P:/.claude/.artifacts/{terminal_id}/identity.json

/id skill fires
  → reads WT_SESSION from env
  → reads identity cache
  → validates and reports
```
