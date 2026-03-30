# Quality Scoring

## Quality Scoring Algorithm

The handoff package implements a multi-component quality scoring algorithm:

| Component | Weight | Description |
|-----------|--------|-------------|
| Completion Tracking | 30% | Resolved issues vs total modifications |
| Action-Outcome Correlation | 25% | Blocker presence indicates incomplete work |
| Decision Documentation | 20% | Number of decisions captured (target: 3+) |
| Issue Resolution | 15% | Absence of blocker indicates resolution |
| Knowledge Contribution | 10% | Patterns learned captured (target: 2+) |

## Quality Ratings

| Score Range | Rating | Description |
|-------------|--------|-------------|
| 0.9-1.0 | Excellent | Comprehensive documentation |
| 0.7-0.8 | Good | Well-documented with minor gaps |
| 0.5-0.6 | Acceptable | Basic documentation with gaps |
| <0.5 | Needs Improvement | Insufficient documentation |

## Quality Breakdown

- Task Completion
- Decision Documentation
- Action-Outcome Link
- Knowledge Capture
- Issue Resolution
