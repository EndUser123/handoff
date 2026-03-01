"""Quality tests for type hint completeness (QUAL-003).

These tests verify that public APIs have complete and specific type hints.
Run with: pytest tests/test_quality_type_hints.py -v

Target: src/handoff/hooks/__lib/transcript.py
Issue: Some public functions have generic or incomplete type hints
"""

import ast
import inspect
from pathlib import Path
from typing import get_type_hints


def get_public_functions(module_path: Path) -> list[tuple[str, inspect.FunctionSignature]]:
    """Extract all public functions from a module.

    Args:
        module_path: Path to the Python module file

    Returns:
        List of (function_name, signature) tuples for non-private functions
    """
    # Read the module source
    source = module_path.read_text()

    # Parse the AST
    tree = ast.parse(source)

    public_functions = []

    # Find all top-level function definitions
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            # Get the signature
            args = []
            for arg in node.args.args:
                arg_annotation = ast.unparse(arg.annotation) if arg.annotation else None
                args.append((arg.arg, arg_annotation))

            # Get return annotation
            return_annotation = ast.unparse(node.returns) if node.returns else None

            public_functions.append((node.name, args, return_annotation))

    return public_functions


def test_extract_topic_from_content_return_type_is_specific():
    """QUAL-003: extract_topic_from_content should have specific return type.

    Given: The extract_topic_from_content function in transcript.py
    When: Inspecting the function signature
    Then: Return type should be more specific than generic 'str'
          (should indicate constraints like max length or valid values)

    Current behavior (BEFORE fix): Returns generic 'str'
    Expected behavior (AFTER fix): Returns TypedDict or Literal indicating constraints
    """
    # Import the module
    from handoff.hooks.__lib import transcript

    # Get the function
    func = transcript.extract_topic_from_content

    # Get type hints with extras to preserve Annotated metadata
    type_hints = get_type_hints(func, include_extras=True)

    # Check return type exists
    assert "return" in type_hints, "extract_topic_from_content should have return type hint"

    # Check return type is specific (not just str)
    # This FAILS because current implementation uses generic 'str'
    return_type = type_hints["return"]

    # After fix, this should pass with a more specific type
    # For now, this FAILS because return type is generic 'str'
    specific_return_types = (
        "Literal",  # For specific keyword values
        "TypedDict",  # For structured return
        "Annotated",  # For constrained str (e.g., Annotated[str, "max_length=80"])
    )

    has_specific_type = any(t in str(return_type) for t in specific_return_types)

    assert has_specific_type, (
        f"Return type should be specific (Literal/TypedDict/Annotated), "
        f"but got generic '{return_type}'. "
        f"Function should indicate that return value is constrained "
        f"(max 80 chars, or specific keyword set)."
    )


def test_detect_structure_type_return_type_specificity():
    """QUAL-003: detect_structure_type should have specific return type structure.

    Given: The detect_structure_type function
    When: Inspecting the return type annotation
    Then: Return type should use TypedDict with specific fields, not dict[str, Any]

    Current behavior (BEFORE fix): Returns dict[str, Any] | None
    Expected behavior (AFTER fix): Returns specific TypedDict | None
    """
    from handoff.hooks.__lib import transcript

    # Get the function
    func = transcript.detect_structure_type

    # Get type hints with extras to preserve Annotated metadata
    type_hints = get_type_hints(func, include_extras=True)

    # Check return type
    assert "return" in type_hints, "detect_structure_type should have return type hint"

    return_type = str(type_hints["return"])

    # This FAILS because current implementation uses generic 'dict[str, Any]'
    # After fix, should use TypedDict with specific fields
    # Check for TypedDict, the specific StructureInfo class, or field names
    assert (
        "TypedDict" in return_type
        or "StructureInfo" in return_type
        or '"type"' in return_type
    ), (
        f"Return type should be TypedDict with specific fields like 'type', 'search_keys', "
        f"but got generic '{return_type}'. "
        f"Generic 'dict[str, Any]' loses type information."
    )


def test_extract_user_message_from_blocker_parameter_specificity():
    """QUAL-003: extract_user_message_from_blocker parameters should be specific.

    Given: The extract_user_message_from_blocker function
    When: Inspecting parameter type hints
    Then: Blocker parameter should use TypedDict instead of dict[str, Any]

    Current behavior (BEFORE fix): Uses dict[str, Any] for blocker parameter
    Expected behavior (AFTER fix): Uses specific TypedDef for blocker structure
    """
    from handoff.hooks.__lib import transcript

    # Get the function
    func = transcript.extract_user_message_from_blocker

    # Get type hints with extras to preserve Annotated metadata
    type_hints = get_type_hints(func, include_extras=True)

    # Check blocker parameter
    assert "blocker" in type_hints, "blocker parameter should have type hint"

    blocker_type = str(type_hints["blocker"])

    # This FAILS because current implementation uses generic 'dict[str, Any]'
    # After fix, should use TypedDict like BlockerDict with specific 'description' field
    assert "TypedDict" in blocker_type or "BlockerDef" in blocker_type, (
        f"Blocker parameter should use TypedDict with specific structure, "
        f"but got generic '{blocker_type}'. "
        f"Function expects 'description' field - should be explicitly typed."
    )


def test_all_public_functions_have_complete_type_hints():
    """QUAL-003: All public functions in transcript.py should have complete type hints.

    Given: The transcript.py module
    When: Inspecting all public (non-private) functions
    Then: All parameters and return values should have specific type hints
          (no generic 'dict', 'list', 'Any' without specific types)

    Current behavior (BEFORE fix): Some functions use generic types like dict[str, Any]
    Expected behavior (AFTER fix): All type hints are specific (TypedDict, list[SpecificType], etc.)
    """
    module_path = Path("P:/packages/handoff/src/handoff/hooks/__lib/transcript.py")

    # Get all public functions
    public_functions = get_public_functions(module_path)

    # Track violations
    violations = []

    for func_name, args, return_annotation in public_functions:
        # Check each parameter
        for param_name, param_annotation in args:
            if param_annotation is None:
                violations.append(f"{func_name}.{param_name}: Missing type hint")
            elif "Any" in param_annotation:
                violations.append(f"{func_name}.{param_name}: Uses 'Any' (should be specific)")

        # Check return annotation
        if return_annotation is None:
            violations.append(f"{func_name}: Missing return type hint")
        elif "Any" in return_annotation:
            violations.append(f"{func_name}: Return type uses 'Any' (should be specific)")
        elif return_annotation in ["dict", "list", "tuple"]:
            violations.append(
                f"{func_name}: Return type is generic '{return_annotation}' "
                f"(should specify element types)"
            )

    # This FAILS because multiple functions use generic types
    assert not violations, (
        "Public functions should have complete, specific type hints.\n"
        f"Found {len(violations)} violations:\n" + "\n".join(f"  - {v}" for v in violations)
    )


def test_mypy_strict_mode_passes():
    """QUAL-003: transcript.py should pass mypy strict type checking.

    Given: The transcript.py module
    When: Running mypy with strict mode
    Then: No type errors should be reported

    Current behavior (BEFORE fix): May have type errors or warnings
    Expected behavior (AFTER fix): Passes mypy --strict
    """
    import subprocess

    result = subprocess.run(
        [
            "mypy",
            "P:/packages/handoff/src/handoff/hooks/__lib/transcript.py",
            "--strict",
            "--show-error-codes",
        ],
        capture_output=True,
        text=True,
    )

    # This FAILS if mypy reports any errors
    assert result.returncode == 0, (
        f"transcript.py should pass mypy strict type checking.\n"
        f"Exit code: {result.returncode}\n"
        f"Output:\n{result.stdout}\n"
        f"Errors:\n{result.stderr}"
    )


def test_public_api_type_completeness():
    """QUAL-003: Public API functions should not use generic dict/return types.

    This is a comprehensive test that verifies:
    1. All public functions have type hints
    2. Return types are specific (not dict[str, Any] or similar)
    3. Parameter types are specific

    Given: Public API functions in transcript.py
    When: Analyzing type hints
    Then: All types should be specific and informative

    Current behavior (BEFORE fix): Generic types used in several functions
    Expected behavior (AFTER fix): All types use TypedDict or specific classes
    """
    from handoff.hooks.__lib import transcript

    # List of public functions to check (non-private, not test fixtures)
    public_functions = [
        transcript.extract_topic_from_content,
        transcript.detect_structure_type,
        transcript.extract_user_message_from_blocker,
        transcript.filter_valid_messages,
        transcript.extract_transcript_from_messages,
    ]

    generic_type_patterns = [
        r"dict\[str,\s*Any\]",  # Too generic
        r"list\[Any\]",  # Too generic
        r"dict\[str,\s*str\]",  # Sometimes OK, but often should be TypedDict
        r"\[Any\]",  # Any in unions
    ]

    violations = []

    for func in public_functions:
        func_name = func.__name__
        type_hints = get_type_hints(func)

        # Check all hints for generic patterns
        for param_name, param_type in type_hints.items():
            param_type_str = str(param_type)

            for pattern in generic_type_patterns:
                import re

                if re.search(pattern, param_type_str):
                    violations.append(
                        f"{func_name}.{param_name}: Generic type '{param_type_str}' "
                        f"(matches pattern '{pattern}')"
                    )

    # This FAILS because multiple functions use generic types
    assert not violations, (
        "Public API should use specific types, not generic dict/list/Any.\n"
        f"Found {len(violations)} violations:\n" + "\n".join(f"  - {v}" for v in violations)
    )
