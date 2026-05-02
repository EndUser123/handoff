# Core Features

## Work Context Structure

**Session Metadata**: Session ID, quality score (0-1), duration, working directory

**Core Components**:
- **Final Actions**: What was completed with evidence and priority
- **Outcomes**: Success/partial/failed outcomes with status tracking
- **Active Work**: Current work in progress with priority ranking
- **Working Decisions**: Key decisions for continuity
- **Tasks Snapshot**: Task status with priority and effort estimation
- **Known Issues**: Problems with resolution hints and priority
- **Open Questions**: Clarification needs with categorization

**Enhanced Context**:
- **Session Objectives**: Primary goals with priority and status
- **Knowledge Contributions**: Insights and patterns learned
- **Quality Metrics**: Session effectiveness scoring

## Automated Context Detection
- **Git Status Analysis**: Detect active work from git changes
- **Recent File Activity**: Identify modified files in last hour
- **Project Fingerprinting**: Quick project analysis
- **Session State Validation**: Verify context consistency

## Quality Scoring Algorithm

| Component | Weight | Description |
|-----------|--------|-------------|
| Completion Tracking | 30% | Resolved issues vs total modifications |
| Action-Outcome Correlation | 25% | Blocker presence indicates incomplete work |
| Decision Documentation | 20% | Number of decisions captured (target: 3+) |
| Issue Resolution | 15% | Absence of blocker indicates resolution |
| Knowledge Contribution | 10% | Patterns learned captured (target: 2+) |

**Quality Ratings**:
- **0.9-1.0**: Excellent - Comprehensive documentation
- **0.7-0.8**: Good - Well-documented with minor gaps
- **0.5-0.6**: Acceptable - Basic documentation with gaps
- **<0.5**: Needs Improvement
