#!/usr/bin/env bash
# retry_haiku.sh — spawn Haiku summarization with retry and non-fatal failure.
# Usage: bash retry_haiku.sh <transcript_path> <output_path> <prompt_file>
# On Windows (Git Bash): uses CREATE_NEW_PROCESS_GROUP via Python subprocess
# On Unix: uses nohup + background

set -e

TRANSCRIPT="$1"
OUTPUT="$2"
PROMPT_FILE="$3"

LOG_DIR="${LOG_DIR:-$HOME/.claude/logs}"
LOG_FILE="$LOG_DIR/retry_haiku.log"

mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%dT%H:%M:%S')] retry_haiku: $*" >> "$LOG_FILE"
}

log "Starting: transcript=$TRANSCRIPT output=$OUTPUT"

# Platform detection
IS_WINDOWS=false
case "$(uname -s)" in
    CYGWIN*|MINGW*|MSYS*) IS_WINDOWS=true ;;
esac

# Retry wrapper
max_retries=3
delays=(0 2 4)  # seconds

for i in $(seq 0 $((max_retries - 1))); do
    if [ $i -gt 0 ]; then
        log "Retry $i after ${delays[$i]}s delay"
        sleep "${delays[$i]}"
    fi

    # Build claude command
    prompt_content=$(cat "$PROMPT_FILE")

    if [ "$IS_WINDOWS" = true ]; then
        # Windows: use Python to spawn with CREATE_NEW_PROCESS_GROUP
        python - <<'PY'
import subprocess
import sys
import os

transcript = sys.argv[1]
output = sys.argv[2]
prompt_content = sys.argv[3]

env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

try:
    proc = subprocess.Popen(
        [
            "claude",
            "-p", prompt_content,
            "--output-format", "json",
            "--model", "haiku",
            "--max-turns", "1",
        ],
        env=env,
        cwd="/tmp",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP') else 0,
    )
    stdout, stderr = proc.communicate(timeout=120)
    if proc.returncode == 0:
        with open(output, "w", encoding="utf-8") as f:
            f.write(stdout.decode("utf-8", errors="replace"))
        sys.exit(0)
    else:
        sys.exit(proc.returncode)
except Exception as e:
    sys.exit(1)
PY
        rc=$?
    else
        # Unix: background with nohup, wait for completion
        nohup claude -p "$prompt_content" --output-format json --model haiku --max-turns 1 > "$OUTPUT" 2>&1 &
        local_pid=$!
        sleep 120  # Wait for Haiku to complete (max 120s timeout)
        if kill -0 $local_pid 2>/dev/null; then
            kill $local_pid 2>/dev/null
            rc=124  # Timeout
        else
            wait $local_pid
            rc=$?
        fi
    fi

    if [ $rc -eq 0 ]; then
        log "Success on attempt $((i+1))"
        exit 0
    fi

    log "Attempt $((i+1)) failed with exit code $rc"
done

log "All $max_retries retries failed — exiting 0 (non-fatal)"
exit 0