#\!/usr/bin/env python3
"""CSF NIP Sub-Agent Invocation Example"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

@dataclass
class SubAgentTask:
    """SubAgentTask dataclass for CSF NIP sub-agent invocation."""
    subagent_type: str
    task_description: str
    task_context: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    metadata: dict = field(default_factory=dict)

    def format_for_task_tool(self) -> dict:
        return {
            "subagent_type": self.subagent_type,
            "task_description": self.task_description,
            "task_context": self.task_context,
        }

    def to_yaml_comment_block(self) -> str:
        return f"# Task tool invocation for {self.subagent_type}:\n#\n# Task:\n#   subagent_type: {self.subagent_type}\n#   task_description: |\n#     {self.task_description}\n#   task_context: |\n#     {self.task_context}"

def create_discovery_orchestrator_task(goal, search_paths, constraints, relevant_patterns=None):
    context_parts = [
        f"Goal: {goal}",
        f"Search paths: {chr(44).join(search_paths)}",
        f"Constraints: {chr(44).join(constraints)}",
    ]
    if relevant_patterns:
        context_parts.append(f"Relevant patterns: {relevant_patterns}")
    return SubAgentTask(
        subagent_type="csf-nip-discovery-orchestrator",
        task_description=f"Analyze and document: {goal}",
        task_context="\n".join(context_parts),
        metadata={"search_paths": search_paths, "constraints": constraints, "patterns": relevant_patterns or {}}
    )

def create_investigation_task(target, investigation_type, context):
    return SubAgentTask(
        subagent_type="csf-nip-discovery-orchestrator",
        task_description=f"{investigation_type}: {target}",
        task_context=f"Target: {target}\nType: {investigation_type}\nContext: {context}",
        metadata={"target": target, "investigation_type": investigation_type}
    )

# HOW TO USE THE TASK TOOL IN A CLAUDE CODE SESSION
# =================================================
# The Task tool is used to invoke sub-agents. Use this format:
#
# Task:
#   subagent_type: csf-nip-discovery-orchestrator
#   task_description: |
#     [Clear description of what the sub-agent should do]
#   task_context: |
#     [Background context, search paths, constraints, relevant patterns]
#
# COMMON SUBAGENT TYPES:
# - csf-nip-discovery-orchestrator: File/discovery operations
# - csf-nip-code-review: Code review operations
# - csf-nip-documentation: Documentation operations
# - csf-nip-testing: Test-related operations

if __name__ == "__main__":
    print("=" * 70)
    print("Example: Discovery Orchestrator Task")
    print("=" * 70)
    task = create_discovery_orchestrator_task(
        goal="Find authentication code",
        search_paths=["src/", "lib/"],
        constraints=["Exclude third-party"],
        relevant_patterns={"file_patterns": ["*auth*.py"]}
    )
    print(f"Subagent Type: {task.subagent_type}")
    print(f"Task Description: {task.task_description}")
    print("YAML Format:")
    print(task.to_yaml_comment_block())
    print("=" * 70)
