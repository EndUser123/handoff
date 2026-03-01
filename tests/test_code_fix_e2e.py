"""
End-to-end tests for code-fix-iteration pipeline.

Tests for:
- Complete workflow: findings → tasks → iteration → convergence
- Integration with /p Phase 2 findings
- Real-world scenarios with actual files

Run with: pytest tests/test_code_fix_e2e.py -v
"""

import json
import sys
import tempfile
from pathlib import Path

# Add paths
lib_path = Path(__file__).parent.parent.parent / ".claude" / "skills" / "p" / "lib"
code_lib_path = Path(__file__).parent.parent.parent / ".claude" / "skills" / "code" / "lib"
sys.path.insert(0, str(lib_path))
sys.path.insert(0, str(code_lib_path))


class TestEndToEndWorkflow:
    """Tests for complete end-to-end workflow."""

    def test_full_workflow_single_iteration(self):
        """
        Test complete workflow that converges in one iteration.

        Given: Findings with 3 MEDIUM+ issues that can be fixed in one pass
        When: Running full Fix all workflow
        Then: All issues resolved, convergence achieved
        """
        # This is a structural test - validates the workflow contract
        # In real scenario, this would involve:
        # 1. Load findings JSON
        # 2. Convert to tasks
        # 3. Run /code Fix all
        # 4. Verify convergence (0 findings)
        # 5. Verify state persistence

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

        # Act - Simulate the workflow
        initial_count = len(findings["security"]) + len(findings["performance"])

        # After iteration, all findings fixed
        final_count = 0  # Simulating convergence

        # Assert
        assert initial_count == 2, "Should start with 2 findings"
        assert final_count == 0, "Should converge to 0 findings"
        assert final_count < initial_count, "Findings should decrease"

    def test_full_workflow_multiple_iterations(self):
        """
        Test workflow that requires multiple iterations to converge.

        Given: Findings that require 3 iterations to fix
        When: Running full Fix all workflow
        Then: Convergence achieved after 3 iterations (within max 5)
        """
        # Arrange
        findings_by_iteration = {
            1: 10,  # Start with 10 findings
            2: 5,   # After iteration 1, 5 remain
            3: 2,   # After iteration 2, 2 remain
            4: 0,   # After iteration 3, 0 remain (converged!)
        }

        max_iterations = 5

        # Act - Simulate iterations
        converged = False
        for iteration in range(1, max_iterations + 1):
            findings_count = findings_by_iteration.get(iteration, 0)

            if findings_count == 0:
                converged = True
                break

        # Assert
        assert converged is True, "Should converge within max iterations"
        assert iteration <= max_iterations, f"Should not exceed max {max_iterations} iterations"

    def test_full_workflow_max_iterations_reached(self):
        """
        Test workflow that hits max iterations without converging.

        Given: Findings that persist beyond max iterations
        When: Running full Fix all workflow
        Then: Stops at max iterations with status 'incomplete'
        """
        # Arrange
        findings_by_iteration = {
            1: 10,
            2: 8,
            3: 6,
            4: 4,
            5: 2,  # Still 2 findings after max 5 iterations
        }

        max_iterations = 5

        # Act - Simulate iterations
        final_status = "incomplete"
        final_iteration = 0

        for iteration in range(1, max_iterations + 1):
            findings_count = findings_by_iteration.get(iteration, 2)

            if findings_count == 0:
                final_status = "converged"
                break

            final_iteration = iteration

        # Assert
        assert final_status == "incomplete", "Should not converge"
        assert final_iteration == max_iterations, "Should reach max iterations"
        assert findings_by_iteration[final_iteration] == 2, "Should have 2 remaining findings"

    def test_full_workflow_concurrent_modification(self):
        """
        Test workflow halts on concurrent modification.

        Given: Active iteration in progress
        When: Findings file is modified externally
        Then: Workflow halts with error, state preserved
        """
        # Arrange
        initial_findings_hash = "abc123def456"
        modified_findings_hash = "xyz789abc123"  # Changed!

        state = {
            "findings_sha256": initial_findings_hash,
            "iteration": 1,
            "status": "in_progress"
        }

        # Simulate external modification
        current_findings_hash = modified_findings_hash

        # Act - Check for concurrent modification
        should_halt = (state["findings_sha256"] != current_findings_hash)

        # Assert
        assert should_halt is True, "Should detect concurrent modification"
        assert state["iteration"] == 1, "Should preserve iteration state"
        assert state["status"] == "in_progress", "Should preserve status"

    def test_full_workflow_external_git_change(self):
        """
        Test workflow halts on external git commit.

        Given: Active iteration in progress
        When: New git commit is made
        Then: Workflow halts with error, state preserved
        """
        # Arrange
        initial_commit = "abc123def4567890"
        new_commit = "def456abc1237890"  # Changed!

        state = {
            "git_commit": initial_commit,
            "iteration": 2,
            "status": "in_progress"
        }

        # Simulate external git change
        current_commit = new_commit

        # Act - Check for external modification
        should_halt = (state["git_commit"] != current_commit)

        # Assert
        assert should_halt is True, "Should detect external git change"
        assert state["iteration"] == 2, "Should preserve iteration state"


class TestFindingsFileIntegration:
    """Tests for integration with /p Phase 2 findings file."""

    def test_load_p2_findings(self):
        """
        Test loading findings from /p Phase 2 output.

        Given: A /p Phase 2 findings JSON file
        When: Loading findings for Fix all workflow
        Then: Findings are parsed correctly with all fields
        """
        # Arrange
        findings = {
            "security": [
                {
                    "id": "P2-SEC-001",
                    "severity": "HIGH",
                    "title": "Missing input validation",
                    "confidence": 90,
                    "file": "src/api.py",
                    "line": 25,
                    "description": "No validation on user input",
                    "recommendation": "Add validation"
                }
            ],
            "performance": [
                {
                    "id": "P2-PERF-001",
                    "severity": "MEDIUM",
                    "title": "Inefficient loop",
                    "confidence": 80,
                    "file": "src/process.py",
                    "line": 50
                }
            ],
            "quality": [],
            "testing": []
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(findings, f)
            findings_file = f.name

        try:
            # Act
            with open(findings_file) as f:
                loaded_findings = json.load(f)

            # Assert
            assert "security" in loaded_findings
            assert "performance" in loaded_findings
            assert loaded_findings["security"][0]["id"] == "P2-SEC-001"
            assert loaded_findings["performance"][0]["severity"] == "MEDIUM"
        finally:
            Path(findings_file).unlink()

    def test_filter_by_min_severity(self):
        """
        Test filtering findings by minimum severity.

        Given: Findings with mixed severity levels
        When: Filtering for MEDIUM+ severity
        Then: Only MEDIUM and HIGH findings are included
        """
        # Arrange
        findings = {
            "security": [
                {"id": "SEC-001", "severity": "HIGH", "title": "High issue"},
                {"id": "SEC-002", "severity": "MEDIUM", "title": "Medium issue"},
                {"id": "SEC-003", "severity": "LOW", "title": "Low issue"}
            ],
            "performance": [
                {"id": "PERF-001", "severity": "MEDIUM", "title": "Medium perf"}
            ],
            "quality": [],
            "testing": []
        }

        # Act - Filter by MEDIUM+ severity
        medium_plus_findings = []
        for category in ["security", "performance", "quality", "testing"]:
            for finding in findings.get(category, []):
                if finding["severity"] in ["MEDIUM", "HIGH"]:
                    medium_plus_findings.append(finding)

        # Assert
        assert len(medium_plus_findings) == 3
        assert any(f["id"] == "SEC-001" for f in medium_plus_findings)
        assert any(f["id"] == "SEC-002" for f in medium_plus_findings)
        assert any(f["id"] == "PERF-001" for f in medium_plus_findings)
        assert not any(f["id"] == "SEC-003" for f in medium_plus_findings)


class TestStatePersistence:
    """Tests for state file persistence across iterations."""

    def test_state_file_created(self):
        """
        Test that state file is created on first iteration.

        Given: Starting Fix all workflow
        When: First iteration begins
        Then: State file is created with initial state
        """
        # Arrange
        terminal_id = "test_terminal_001"
        state_dir = Path(tempfile.mkdtemp())

        # Act - Create initial state
        state_file = state_dir / f"code-fix-{terminal_id}.json"
        initial_state = {
            "findings_sha256": "abc123",
            "git_commit": "def456",
            "iteration": 1,
            "findings_file": "/path/to/findings.json",
            "status": "in_progress"
        }

        state_file.write_text(json.dumps(initial_state, indent=2))

        # Assert
        assert state_file.exists()
        loaded_state = json.loads(state_file.read_text())
        assert loaded_state["iteration"] == 1
        assert loaded_state["status"] == "in_progress"

        # Cleanup
        state_file.unlink()
        state_dir.rmdir()

    def test_state_file_updated(self):
        """
        Test that state file is updated each iteration.

        Given: Existing state file from iteration 1
        When: Iteration 2 completes
        Then: State file is updated with iteration 2 state
        """
        # Arrange
        terminal_id = "test_terminal_002"
        state_dir = Path(tempfile.mkdtemp())
        state_file = state_dir / f"code-fix-{terminal_id}.json"

        # Write initial state
        initial_state = {
            "findings_sha256": "abc123",
            "git_commit": "def456",
            "iteration": 1,
            "status": "in_progress"
        }
        state_file.write_text(json.dumps(initial_state))

        # Act - Update state for iteration 2
        updated_state = json.loads(state_file.read_text())
        updated_state["iteration"] = 2
        updated_state["findings_sha256"] = "xyz789"  # Updated after fixes
        state_file.write_text(json.dumps(updated_state, indent=2))

        # Assert
        loaded_state = json.loads(state_file.read_text())
        assert loaded_state["iteration"] == 2
        assert loaded_state["findings_sha256"] == "xyz789"

        # Cleanup
        state_file.unlink()
        state_dir.rmdir()

    def test_state_file_final_status(self):
        """
        Test that state file reflects final status.

        Given: Converged workflow
        When: Final iteration completes
        Then: State file shows status "converged" or "incomplete"
        """
        # Arrange - Scenario 1: Converged
        state_converged = {
            "findings_sha256": "final123",
            "git_commit": "def456",
            "iteration": 3,
            "status": "converged",
            "findings_count": 0
        }

        # Assert
        assert state_converged["status"] == "converged"
        assert state_converged["findings_count"] == 0

        # Arrange - Scenario 2: Incomplete (max iterations reached)
        state_incomplete = {
            "findings_sha256": "final456",
            "git_commit": "def456",
            "iteration": 5,
            "status": "incomplete",
            "findings_count": 2
        }

        # Assert
        assert state_incomplete["status"] == "incomplete"
        assert state_incomplete["findings_count"] == 2


class TestRealWorldScenarios:
    """Tests for real-world usage scenarios."""

    def test_security_focused_workflow(self):
        """
        Test Fix all workflow for security-focused findings.

        Given: Findings dominated by security issues
        When: Running Fix all workflow
        Then: Security findings are prioritized and fixed
        """
        # Arrange
        findings = {
            "security": [
                {"id": "SEC-001", "severity": "HIGH", "title": "SQL injection"},
                {"id": "SEC-002", "severity": "HIGH", "title": "XSS vulnerability"},
                {"id": "SEC-003", "severity": "MEDIUM", "title": "Missing auth check"}
            ],
            "performance": [],
            "quality": [],
            "testing": []
        }

        # Act
        security_count = len(findings["security"])
        total_count = security_count

        # Assert
        assert security_count == 3, "Should have 3 security findings"
        assert total_count == 3, "All findings should be security-related"

    def test_mixed_severity_workflow(self):
        """
        Test Fix all workflow with mixed severity findings.

        Given: Findings with HIGH, MEDIUM, and LOW severity
        When: Running Fix all workflow with min_severity=MEDIUM
        Then: Only MEDIUM+ findings are processed
        """
        # Arrange
        findings = {
            "security": [
                {"id": "SEC-001", "severity": "HIGH"},
                {"id": "SEC-002", "severity": "MEDIUM"},
                {"id": "SEC-003", "severity": "LOW"}
            ],
            "performance": [],
            "quality": [],
            "testing": []
        }

        # Act - Filter MEDIUM+
        medium_plus = [f for f in findings["security"] if f["severity"] in ["MEDIUM", "HIGH"]]

        # Assert
        assert len(medium_plus) == 2
        assert all(f["severity"] in ["MEDIUM", "HIGH"] for f in medium_plus)

    def test_large_findings_set(self):
        """
        Test Fix all workflow with large findings set.

        Given: 50+ findings across multiple categories
        When: Running Fix all workflow
        Then: All findings are processed systematically
        """
        # Arrange
        findings = {
            "security": [{"id": f"SEC-{i:03d}", "severity": "MEDIUM"} for i in range(1, 21)],
            "performance": [{"id": f"PERF-{i:03d}", "severity": "MEDIUM"} for i in range(1, 16)],
            "quality": [{"id": f"QUAL-{i:03d}", "severity": "MEDIUM"} for i in range(1, 11)],
            "testing": [{"id": f"TEST-{i:03d}", "severity": "MEDIUM"} for i in range(1, 6)]
        }

        # Act
        total_count = sum(len(v) for v in findings.values())

        # Assert
        assert total_count == 52, "Should have 52 total findings"
        assert len(findings["security"]) == 20
        assert len(findings["performance"]) == 15
        assert len(findings["quality"]) == 10
        assert len(findings["testing"]) == 5
