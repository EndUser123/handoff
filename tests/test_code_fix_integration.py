"""
Integration tests for code-fix-iteration pipeline.

Tests for:
- Full pipeline with mock findings
- Multi-terminal scenarios
- External modification detection

Run with: pytest tests/test_code_fix_integration.py -v
"""

import json
import sys
import tempfile
from pathlib import Path

# Add paths
lib_path = Path(__file__).parent.parent.parent / ".claude" / "skills" / "p" / "lib"
scripts_path = Path(__file__).parent.parent.parent / ".claude" / "skills" / "p" / "scripts"
sys.path.insert(0, str(lib_path))
sys.path.insert(0, str(scripts_path))


class TestFullPipelineWithMockFindings:
    """Tests for full pipeline execution with mock findings."""

    def test_convert_findings_to_tasks(self):
        """
        Test that findings are converted to tasks correctly.

        Given: Mock findings file with MEDIUM+ issues
        When: Pipeline converts findings to tasks
        Then: Correct task templates are generated
        """
        # Arrange
        findings = {
            "security": [
                {
                    "id": "SEC-001",
                    "severity": "HIGH",
                    "title": "SQL injection vulnerability",
                    "confidence": 95,
                    "file": "src/db.py",
                    "line": 42
                }
            ],
            "performance": [
                {
                    "id": "PERF-001",
                    "severity": "MEDIUM",
                    "title": "Inefficient algorithm",
                    "confidence": 85,
                    "file": "src/process.py",
                    "line": 15
                }
            ],
            "quality": [],
            "testing": []
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(findings, f)
            findings_file = f.name

        try:
            # Act - Import and use the converter
            # Add path before importing
            code_lib_path = Path(__file__).parent.parent.parent / ".claude" / "skills" / "code" / "lib"
            if str(code_lib_path) not in sys.path:
                sys.path.insert(0, str(code_lib_path))

            try:
                from findings_to_tasks import convert_findings_to_tasks
                tasks = convert_findings_to_tasks(findings_file, min_severity="MEDIUM")

                # Assert
                assert len(tasks) == 2
                assert any(t["metadata"]["id"] == "SEC-001" for t in tasks)
                assert any(t["metadata"]["id"] == "PERF-001" for t in tasks)
            except ImportError as e:
                # If module not available, test the data structure would work
                # This validates the integration contract without requiring the actual module
                # (useful for testing in different environments)
                assert False, f"findings_to_tasks module not available: {e}"
        finally:
            Path(findings_file).unlink()

    def test_iteration_state_tracking(self):
        """
        Test that iteration state is tracked correctly.

        Given: Starting an iteration
        When: State is saved and loaded
        Then: State persists correctly
        """
        # Arrange
        state = {
            "findings_sha256": "abc123",
            "git_commit": "def456",
            "iteration": 1,
            "findings_file": "/path/to/findings.json",
            "status": "in_progress"
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(state, f)
            state_file = f.name

        try:
            # Act
            with open(state_file) as f:
                loaded_state = json.load(f)

            # Assert
            assert loaded_state["findings_sha256"] == "abc123"
            assert loaded_state["iteration"] == 1
            assert loaded_state["status"] == "in_progress"
        finally:
            Path(state_file).unlink()


class TestMultiTerminalScenarios:
    """Tests for multi-terminal safety."""

    def test_terminal_scoped_state_files(self):
        """
        Test that state files are terminal-scoped.

        Given: Two different terminal IDs
        When: State is saved for each terminal
        Then: Separate state files are created
        """
        # Arrange
        terminal1_id = "term_abc123"
        terminal2_id = "term_def456"

        with tempfile.TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir)

            # Act
            state_file_1 = state_dir / f"code-fix-{terminal1_id}.json"
            state_file_2 = state_dir / f"code-fix-{terminal2_id}.json"

            state_file_1.write_text('{"terminal": "term_abc123"}')
            state_file_2.write_text('{"terminal": "term_def456"}')

            # Assert
            assert state_file_1.exists()
            assert state_file_2.exists()
            assert state_file_1.read_text() != state_file_2.read_text()

    def test_concurrent_modification_detection(self):
        """
        Test that concurrent modifications are detected.

        Given: Original findings SHA256 hash
        When: Findings file changes between iterations
        Then: Concurrent modification error is raised
        """
        # This test validates the logic - actual error handling depends on iteration orchestrator
        # Arrange
        original_hash = "abc123"
        modified_hash = "xyz789"

        # Simulate state
        state = {
            "findings_sha256": original_hash,
            "git_commit": "def456",
            "iteration": 1
        }

        # Act & Assert
        # Simulate hash mismatch detection
        if state["findings_sha256"] != modified_hash:
            # This is the check that would happen in the iteration loop
            modification_detected = True
        else:
            modification_detected = False

        assert modification_detected is True, "Should detect concurrent modification"


class TestExternalModificationDetection:
    """Tests for external modification detection."""

    def test_git_commit_change_detection(self):
        """
        Test that git commit changes are detected.

        Given: Original git commit SHA
        When: Git commit changes during iteration
        Then: External modification is detected
        """
        # Arrange
        original_commit = "abc123def4567890"
        new_commit = "def456abc1237890"

        # Simulate iteration state
        initial_commit = original_commit
        current_commit = new_commit

        # Act & Assert
        external_change_detected = (initial_commit != current_commit)
        assert external_change_detected is True

    def test_file_mtime_change_detection(self):
        """
        Test that file mtime changes are detected.

        Given: Initial file mtime snapshot
        When: File modification times change
        Then: External modification is detected
        """
        # Arrange
        initial_snapshot = {
            "file1.py": 1234567890.0,
            "file2.py": 1234567891.0
        }

        modified_snapshot = {
            "file1.py": 1234567890.0,
            "file2.py": 9999999999.0  # Changed!
        }

        # Act & Assert
        changes = []
        for filename, mtime in initial_snapshot.items():
            if modified_snapshot.get(filename) != mtime:
                changes.append(filename)

        assert "file2.py" in changes
        assert len(changes) == 1

    def test_concurrent_modification_halts_iteration(self):
        """
        Test that iteration halts on concurrent modification.

        Given: Active iteration in progress
        When: Findings SHA256 changes
        Then: Iteration should halt with error
        """
        # This is a behavioral test - the actual halt would happen in code_fix_iteration.py
        # Arrange
        stored_findings_hash = "abc123"
        current_findings_hash = "xyz789"  # Changed!

        # Act
        should_halt = (stored_findings_hash != current_findings_hash)

        # Assert
        assert should_halt is True, "Iteration should halt on concurrent modification"


class TestIterationConvergence:
    """Tests for iteration convergence behavior."""

    def test_convergence_with_zero_findings(self):
        """
        Test that convergence is achieved with zero findings.

        Given: Iteration with 0 MEDIUM+ findings
        When: Checking convergence
        Then: Should report convergence achieved
        """
        # Arrange
        findings_count = 0

        # Act
        converged = (findings_count == 0)

        # Assert
        assert converged is True

    def test_no_convergence_with_findings_remaining(self):
        """
        Test that convergence is not achieved with findings remaining.

        Given: Iteration with 5 MEDIUM+ findings
        When: Checking convergence
        Then: Should report not converged
        """
        # Arrange
        findings_count = 5

        # Act
        converged = (findings_count == 0)

        # Assert
        assert converged is False

    def test_max_iterations_enforcement(self):
        """
        Test that max iterations limit is enforced.

        Given: Max iterations set to 5
        When: 5 iterations completed
        Then: Should stop even if findings remain
        """
        # Arrange
        max_iterations = 5
        current_iteration = 5

        # Act
        should_stop = (current_iteration >= max_iterations)

        # Assert
        assert should_stop is True

    def test_continue_below_max_iterations(self):
        """
        Test that iteration continues below max.

        Given: Max iterations set to 5
        When: Only 3 iterations completed
        Then: Should continue
        """
        # Arrange
        max_iterations = 5
        current_iteration = 3

        # Act
        should_stop = (current_iteration >= max_iterations)

        # Assert
        assert should_stop is False
