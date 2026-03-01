"""
Tests for findings-to-tasks converter.

These tests verify that adversarial review findings can be converted
to /code task templates for the iterative fix-all workflow.

Run with: pytest tests/test_findings_to_tasks.py -v
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

# Add the lib directory to Python path for the code skill library
# From tests/ go up to project root (P:/), then to .claude/skills/code/lib
if TYPE_CHECKING:
    from findings_to_tasks import convert_findings_to_tasks
else:
    lib_path = Path(__file__).parent.parent.parent.parent / ".claude" / "skills" / "code" / "lib"
    sys.path.insert(0, str(lib_path))
    from findings_to_tasks import convert_findings_to_tasks


def _create_temp_findings_file(findings_data: dict) -> Path:
    """Create a temporary JSON file with findings data.

    Args:
        findings_data: Dictionary containing findings to write

    Returns:
        Path to the temporary file
    """
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(findings_data, f)
    f.close()
    return Path(f.name)


def _base_finding(
    finding_id: str,
    severity: str,
    title: str,
    file_path: str = "src/file.py",
    line: int = 1,
) -> dict:
    """Create a base finding dictionary with common fields.

    Args:
        finding_id: Unique identifier for the finding
        severity: Severity level (CRITICAL, HIGH, MEDIUM, LOW)
        title: Brief title describing the finding
        file_path: Path to the file with the finding
        line: Line number of the finding

    Returns:
        Dictionary with finding data
    """
    return {
        "id": finding_id,
        "severity": severity,
        "title": title,
        "confidence": 95,
        "file": file_path,
        "line": line,
        "description": f"Description for {finding_id}",
        "recommended_action": f"Fix {finding_id}",
    }


class TestConvertCriticalFindings:
    """Tests for CRITICAL severity findings conversion."""

    def test_convert_critical_findings(self) -> None:
        """
        Test that CRITICAL severity findings are converted to tasks.

        Given: A findings file with CRITICAL severity findings
        When: convert_findings_to_tasks is called with min_severity="MEDIUM"
        Then: CRITICAL findings are converted to tasks
        """
        # Arrange
        findings_data = {
            "security": [],
            "performance": [],
            "quality": [],
            "testing": [
                {
                    "id": "TEST-001",
                    "severity": "CRITICAL",
                    "title": "No unit tests for validate_templates.py",
                    "confidence": 100,
                    "file": "src/validate_templates.py",
                    "line": 1,
                    "description": "Missing test coverage",
                    "recommended_action": "Add unit tests"
                }
            ]
        }

        findings_file = _create_temp_findings_file(findings_data)
        try:
            # Act
            tasks = convert_findings_to_tasks(str(findings_file), min_severity="MEDIUM")

            # Assert
            assert len(tasks) == 1
            assert tasks[0]["subject"] == "Add unit tests for validate_templates.py"
            assert "TEST-001" in tasks[0]["description"]
            assert tasks[0]["metadata"]["severity"] == "CRITICAL"
            assert tasks[0]["metadata"]["id"] == "TEST-001"
        finally:
            findings_file.unlink()


class TestConvertHighFindings:
    """Tests for HIGH severity findings conversion."""

    def test_convert_high_findings(self) -> None:
        """
        Test that HIGH severity findings are converted to tasks.

        Given: A findings file with HIGH severity findings
        When: convert_findings_to_tasks is called with min_severity="MEDIUM"
        Then: HIGH findings are converted to tasks
        """
        # Arrange
        findings_data = {
            "security": [],
            "performance": [
                {
                    "id": "PERF-001",
                    "severity": "HIGH",
                    "title": "Redundant file reads",
                    "confidence": 95,
                    "file": "src/config.py",
                    "line": 42,
                    "description": "File read in loop",
                    "recommended_action": "Cache file content"
                }
            ],
            "quality": [],
            "testing": []
        }

        findings_file = _create_temp_findings_file(findings_data)
        try:
            # Act
            tasks = convert_findings_to_tasks(str(findings_file), min_severity="MEDIUM")

            # Assert
            assert len(tasks) == 1
            assert tasks[0]["subject"] == "Fix redundant file reads"
            assert "PERF-001" in tasks[0]["description"]
            assert tasks[0]["metadata"]["severity"] == "HIGH"
            assert tasks[0]["metadata"]["id"] == "PERF-001"
        finally:
            findings_file.unlink()


class TestConvertMediumFindings:
    """Tests for MEDIUM severity findings conversion."""

    def test_convert_medium_findings(self) -> None:
        """
        Test that MEDIUM severity findings are converted to tasks.

        Given: A findings file with MEDIUM severity findings
        When: convert_findings_to_tasks is called with min_severity="MEDIUM"
        Then: MEDIUM findings are converted to tasks
        """
        # Arrange
        findings_data = {
            "security": [],
            "performance": [
                {
                    "id": "PERF-002",
                    "severity": "MEDIUM",
                    "title": "Inefficient duplicate detection O(n*m)",
                    "confidence": 85,
                    "file": "src/duplicates.py",
                    "line": 15,
                    "description": "Quadratic algorithm",
                    "recommended_action": "Use hash-based detection"
                }
            ],
            "quality": [],
            "testing": []
        }

        findings_file = _create_temp_findings_file(findings_data)
        try:
            # Act
            tasks = convert_findings_to_tasks(str(findings_file), min_severity="MEDIUM")

            # Assert
            assert len(tasks) == 1
            assert tasks[0]["subject"] == "Fix inefficient duplicate detection O(n*m)"
            assert "PERF-002" in tasks[0]["description"]
            assert tasks[0]["metadata"]["severity"] == "MEDIUM"
            assert tasks[0]["metadata"]["id"] == "PERF-002"
        finally:
            findings_file.unlink()


class TestFilterLowFindings:
    """Tests for LOW severity findings filtering."""

    def test_filter_low_findings(self) -> None:
        """
        Test that LOW severity findings are filtered out by default.

        Given: A findings file with LOW severity findings
        When: convert_findings_to_tasks is called with default min_severity="MEDIUM"
        Then: LOW findings are not converted to tasks
        """
        # Arrange
        findings_data = {
            "security": [],
            "performance": [
                {
                    "id": "PERF-004",
                    "severity": "LOW",
                    "title": "No caching of validation results",
                    "confidence": 80,
                    "file": "src/validate.py",
                    "line": 10,
                    "description": "Repeated validation",
                    "recommended_action": "Add caching"
                }
            ],
            "quality": [],
            "testing": []
        }

        findings_file = _create_temp_findings_file(findings_data)
        try:
            # Act
            tasks = convert_findings_to_tasks(str(findings_file), min_severity="MEDIUM")

            # Assert
            assert len(tasks) == 0
        finally:
            findings_file.unlink()

    def test_include_low_with_filter(self) -> None:
        """
        Test that LOW severity findings are included when min_severity="LOW".

        Given: A findings file with LOW severity findings
        When: convert_findings_to_tasks is called with min_severity="LOW"
        Then: LOW findings are converted to tasks
        """
        # Arrange
        findings_data = {
            "security": [],
            "performance": [
                {
                    "id": "PERF-004",
                    "severity": "LOW",
                    "title": "No caching of validation results",
                    "confidence": 80,
                    "file": "src/validate.py",
                    "line": 10,
                    "description": "Repeated validation",
                    "recommended_action": "Add caching"
                }
            ],
            "quality": [],
            "testing": []
        }

        findings_file = _create_temp_findings_file(findings_data)
        try:
            # Act
            tasks = convert_findings_to_tasks(str(findings_file), min_severity="LOW")

            # Assert
            assert len(tasks) == 1
            assert tasks[0]["metadata"]["severity"] == "LOW"
            assert tasks[0]["metadata"]["id"] == "PERF-004"
        finally:
            findings_file.unlink()


class TestGroupByFile:
    """Tests for task grouping by file."""

    def test_group_by_file(self) -> None:
        """
        Test that tasks are correctly grouped by file.

        Given: A findings file with findings from multiple files
        When: convert_findings_to_tasks is called
        Then: Tasks maintain file associations in metadata
        """
        # Arrange
        findings_data = {
            "security": [],
            "performance": [
                {
                    "id": "PERF-001",
                    "severity": "HIGH",
                    "title": "Issue in file A",
                    "confidence": 95,
                    "file": "src/file_a.py",
                    "line": 10,
                    "description": "First issue",
                    "recommended_action": "Fix it"
                },
                {
                    "id": "PERF-002",
                    "severity": "MEDIUM",
                    "title": "Issue in file B",
                    "confidence": 85,
                    "file": "src/file_b.py",
                    "line": 20,
                    "description": "Second issue",
                    "recommended_action": "Fix it"
                }
            ],
            "quality": [],
            "testing": []
        }

        findings_file = _create_temp_findings_file(findings_data)
        try:
            # Act
            tasks = convert_findings_to_tasks(str(findings_file), min_severity="MEDIUM")

            # Assert
            assert len(tasks) == 2
            file_paths = {task["metadata"]["file"] for task in tasks}
            assert file_paths == {"src/file_a.py", "src/file_b.py"}
        finally:
            findings_file.unlink()


class TestHandleEmptyFindings:
    """Tests for handling empty findings."""

    def test_handle_empty_findings(self):
        """
        Test that empty findings return empty list.

        Given: A findings file with no findings
        When: convert_findings_to_tasks is called
        Then: Empty list is returned
        """
        # Arrange
        findings_data = {
            "security": [],
            "performance": [],
            "quality": [],
            "testing": []
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(findings_data, f)
            findings_file = f.name

        try:
            # Act
            tasks = convert_findings_to_tasks(findings_file, min_severity="MEDIUM")

            # Assert
            assert tasks == []
        finally:
            Path(findings_file).unlink()


class TestHandleMissingFile:
    """Tests for handling missing files."""

    def test_handle_missing_file(self):
        """
        Test that missing file returns empty list and logs error.

        Given: A findings file that does not exist
        When: convert_findings_to_tasks is called
        Then: Empty list is returned (error logged)
        """
        # Arrange
        findings_file = "/nonexistent/path/to/findings.json"

        # Act
        tasks = convert_findings_to_tasks(findings_file, min_severity="MEDIUM")

        # Assert
        assert tasks == []


class TestHandleInvalidJson:
    """Tests for handling invalid JSON."""

    def test_handle_invalid_json(self):
        """
        Test that invalid JSON returns empty list and logs error.

        Given: A findings file with invalid JSON
        When: convert_findings_to_tasks is called
        Then: Empty list is returned (error logged)
        """
        # Arrange
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{ invalid json }")
            findings_file = f.name

        try:
            # Act
            tasks = convert_findings_to_tasks(findings_file, min_severity="MEDIUM")

            # Assert
            assert tasks == []
        finally:
            Path(findings_file).unlink()


class TestTaskStructure:
    """Tests for task structure validation."""

    def test_task_structure(self):
        """
        Test that tasks have required fields.

        Given: A findings file with valid findings
        When: convert_findings_to_tasks is called
        Then: Tasks have all required fields (subject, description, activeForm, metadata)
        """
        # Arrange
        findings_data = {
            "security": [],
            "performance": [
                {
                    "id": "PERF-001",
                    "severity": "HIGH",
                    "title": "Redundant file reads",
                    "confidence": 95,
                    "file": "src/config.py",
                    "line": 42,
                    "description": "File read in loop",
                    "recommended_action": "Cache file content"
                }
            ],
            "quality": [],
            "testing": []
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(findings_data, f)
            findings_file = f.name

        try:
            # Act
            tasks = convert_findings_to_tasks(findings_file, min_severity="MEDIUM")

            # Assert
            assert len(tasks) == 1
            task = tasks[0]

            # Required fields
            assert "subject" in task
            assert "description" in task
            assert "activeForm" in task
            assert "metadata" in task

            # Subject is imperative and concise
            assert task["subject"]
            assert len(task["subject"]) < 100

            # Description contains finding details
            assert "PERF-001" in task["description"]
            assert "HIGH" in task["description"]
            assert "src/config.py" in task["description"]
            assert "42" in task["description"]

            # activeForm is present continuous
            assert task["activeForm"]
            assert task["activeForm"].startswith("Fixing")

            # Metadata contains original finding data
            assert task["metadata"]["id"] == "PERF-001"
            assert task["metadata"]["severity"] == "HIGH"
            assert task["metadata"]["file"] == "src/config.py"
            assert task["metadata"]["line"] == 42
        finally:
            Path(findings_file).unlink()

    def test_task_structure_missing_optional_fields(self):
        """
        Test that tasks are created even when optional fields are missing.

        Given: A findings file with findings missing optional fields (file, line)
        When: convert_findings_to_tasks is called
        Then: Tasks are created with None for missing fields
        """
        # Arrange
        findings_data = {
            "security": [],
            "performance": [
                {
                    "id": "PERF-001",
                    "severity": "HIGH",
                    "title": "General performance issue",
                    "confidence": 95
                }
            ],
            "quality": [],
            "testing": []
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(findings_data, f)
            findings_file = f.name

        try:
            # Act
            tasks = convert_findings_to_tasks(findings_file, min_severity="MEDIUM")

            # Assert
            assert len(tasks) == 1
            task = tasks[0]
            assert task["metadata"].get("file") is None
            assert task["metadata"].get("line") is None
        finally:
            Path(findings_file).unlink()


class TestSeverityOrdering:
    """Tests for severity ordering and prioritization."""

    def test_severity_ordering_mixed(self):
        """
        Test that findings maintain severity-based ordering.

        Given: A findings file with mixed severity findings
        When: convert_findings_to_tasks is called
        Then: Tasks are ordered by severity (CRITICAL > HIGH > MEDIUM > LOW)
        """
        # Arrange
        findings_data = {
            "security": [],
            "performance": [
                {
                    "id": "PERF-001",
                    "severity": "MEDIUM",
                    "title": "Medium issue",
                    "confidence": 85,
                    "file": "src/file.py",
                    "line": 1
                },
                {
                    "id": "PERF-002",
                    "severity": "CRITICAL",
                    "title": "Critical issue",
                    "confidence": 100,
                    "file": "src/file.py",
                    "line": 2
                },
                {
                    "id": "PERF-003",
                    "severity": "HIGH",
                    "title": "High issue",
                    "confidence": 95,
                    "file": "src/file.py",
                    "line": 3
                }
            ],
            "quality": [],
            "testing": []
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(findings_data, f)
            findings_file = f.name

        try:
            # Act
            tasks = convert_findings_to_tasks(findings_file, min_severity="MEDIUM")

            # Assert
            assert len(tasks) == 3
            severities = [task["metadata"]["severity"] for task in tasks]
            # Should be ordered: CRITICAL, HIGH, MEDIUM
            assert severities == ["CRITICAL", "HIGH", "MEDIUM"]
        finally:
            Path(findings_file).unlink()


class TestMultipleCategories:
    """Tests for handling findings from multiple categories."""

    def test_multiple_categories(self):
        """
        Test that findings from all categories are converted.

        Given: A findings file with findings in security, performance, quality, testing
        When: convert_findings_to_tasks is called
        Then: All findings are converted to tasks regardless of category
        """
        # Arrange
        findings_data = {
            "security": [
                {
                    "id": "SEC-001",
                    "severity": "HIGH",
                    "title": "SQL injection risk",
                    "confidence": 90,
                    "file": "src/db.py",
                    "line": 10
                }
            ],
            "performance": [
                {
                    "id": "PERF-001",
                    "severity": "MEDIUM",
                    "title": "Slow query",
                    "confidence": 85,
                    "file": "src/db.py",
                    "line": 20
                }
            ],
            "quality": [
                {
                    "id": "QUAL-001",
                    "severity": "MEDIUM",
                    "title": "Code duplication",
                    "confidence": 80,
                    "file": "src/utils.py",
                    "line": 5
                }
            ],
            "testing": [
                {
                    "id": "TEST-001",
                    "severity": "CRITICAL",
                    "title": "No test coverage",
                    "confidence": 100,
                    "file": "src/api.py",
                    "line": 1
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(findings_data, f)
            findings_file = f.name

        try:
            # Act
            tasks = convert_findings_to_tasks(findings_file, min_severity="MEDIUM")

            # Assert
            assert len(tasks) == 4
            task_ids = {task["metadata"]["id"] for task in tasks}
            assert task_ids == {"SEC-001", "PERF-001", "QUAL-001", "TEST-001"}
        finally:
            Path(findings_file).unlink()
