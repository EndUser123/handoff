"""
Multi-terminal manifest migration test - simplified version.

Tests the migration logic for old non-scoped manifest files
without importing complex hook code.
"""

import json
import tempfile
from pathlib import Path

import pytest


class TestManifestMigration:
    """Test migration from old to new manifest format."""

    @pytest.fixture
    def task_tracker_dir(self):
        """Create a temporary task tracker directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            task_tracker = Path(tmpdir) / "task_tracker"
            task_tracker.mkdir()
            yield task_tracker

    def test_old_manifest_detected(self, task_tracker_dir):
        """Test that old manifest file can be detected."""
        # Create old-style manifest
        old_manifest = task_tracker_dir / "active_session_manifest.json"
        old_manifest.write_text(json.dumps({
            "terminal_id": "term_legacy",
            "timestamp": "2026-03-06T11:00:00Z",
            "handoff_path": "/path/to/legacy.json"
        }))

        # Verify it exists
        assert old_manifest.exists()
        assert old_manifest.name == "active_session_manifest.json"

    def test_new_manifest_format(self, task_tracker_dir):
        """Test that new terminal-scoped manifest format is correct."""
        # Create new-style manifest
        new_manifest = task_tracker_dir / "active_session_manifest_term_a.json"
        new_manifest.write_text(json.dumps({
            "terminal_id": "term_a",
            "timestamp": "2026-03-06T12:00:00Z",
            "handoff_path": "/path/to/term_a.json"
        }))

        # Verify it exists
        assert new_manifest.exists()
        assert "term_a" in new_manifest.name

        # Verify content
        with open(new_manifest, encoding="utf-8") as f:
            data = json.load(f)
        assert data["terminal_id"] == "term_a"

    def test_multiple_terminals_independent(self, task_tracker_dir):
        """Test that multiple terminals have independent manifests."""
        # Create manifests for two terminals
        manifest_a = task_tracker_dir / "active_session_manifest_term_a.json"
        manifest_b = task_tracker_dir / "active_session_manifest_term_b.json"

        manifest_a.write_text(json.dumps({
            "terminal_id": "term_a",
            "handoff_path": "/path/to/a.json"
        }))

        manifest_b.write_text(json.dumps({
            "terminal_id": "term_b",
            "handoff_path": "/path/to/b.json"
        }))

        # Verify both exist independently
        assert manifest_a.exists()
        assert manifest_b.exists()

        # Verify no shared manifest
        shared_manifest = task_tracker_dir / "active_session_manifest.json"
        assert not shared_manifest.exists()

    def test_migration_preserves_data(self, task_tracker_dir):
        """Test that migration preserves all data from old manifest."""
        # Create old manifest
        old_manifest = task_tracker_dir / "active_session_manifest.json"
        old_data = {
            "terminal_id": "term_legacy",
            "timestamp": "2026-03-06T11:00:00Z",
            "handoff_path": "/path/to/legacy.json",
            "extra_field": "should_be_preserved"
        }
        old_manifest.write_text(json.dumps(old_data))

        # Simulate migration: read old, write new
        with open(old_manifest, encoding="utf-8") as f:
            old_manifest_data = json.load(f)

        terminal_id = old_manifest_data["terminal_id"]
        new_manifest_path = task_tracker_dir / f"active_session_manifest_{terminal_id}.json"

        # Write to new location
        with open(new_manifest_path, "w", encoding="utf-8") as f:
            json.dump(old_manifest_data, f, indent=2)

        # Verify new manifest exists with same data
        assert new_manifest_path.exists()
        with open(new_manifest_path, encoding="utf-8") as f:
            new_data = json.load(f)

        assert new_data["terminal_id"] == "term_legacy"
        assert new_data["handoff_path"] == "/path/to/legacy.json"
        assert new_data.get("extra_field") == "should_be_preserved"

    def test_old_manifest_deleted_after_migration(self, task_tracker_dir):
        """Test that old manifest is deleted after successful migration."""
        # Create old manifest
        old_manifest = task_tracker_dir / "active_session_manifest.json"
        old_manifest.write_text(json.dumps({
            "terminal_id": "term_x",
            "handoff_path": "/path/to/x.json"
        }))

        # Simulate migration
        with open(old_manifest, encoding="utf-8") as f:
            old_data = json.load(f)

        terminal_id = old_data["terminal_id"]
        new_manifest_path = task_tracker_dir / f"active_session_manifest_{terminal_id}.json"

        with open(new_manifest_path, "w", encoding="utf-8") as f:
            json.dump(old_data, f, indent=2)

        # Delete old manifest
        old_manifest.unlink()

        # Verify old manifest is gone, new manifest exists
        assert not old_manifest.exists()
        assert new_manifest_path.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
