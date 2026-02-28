# Badges for handoff

## Single-Line Format

Copy this line to the top of your README.md:

```
[![Build Status](https://img.shields.io/github/actions/status/EndUser123/handoff?branch=main)](https://github.com/EndUser123/handoff/actions) [![Version](https://img.shields.io/pypi/v/handoff)](https://pypi.org/project/handoff/) [![Python](https://img.shields.io/pypi/pyversions/handoff)](https://pypi.org/project/handoff/) [![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT) [![Coverage](https://img.shields.io/codecov/c/github/EndUser123/handoff?token=TODO)](https://codecov.io/gh/EndUser123/handoff)
```

## Individual Badges

| Badge | Description |
|-------|-------------|
| [![Build Status](https://img.shields.io/github/actions/status/EndUser123/handoff?branch=main)](https://github.com/EndUser123/handoff/actions) | GitHub Actions build status |
| [![Version](https://img.shields.io/pypi/v/handoff)](https://pypi.org/project/handoff/) | PyPI package version |
| [![Python](https://img.shields.io/pypi/pyversions/handoff)](https://pypi.org/project/handoff/) | Supported Python versions |
| [![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT) | MIT License |
| [![Coverage](https://img.shields.io/codecov/c/github/EndUser123/handoff?token=TODO)](https://codecov.io/gh/EndUser123/handoff) | Code coverage (requires Codecov setup) |

## Setup Instructions

1. Copy the single-line format to the top of README.md
2. Update repo_name if auto-detection was incorrect
3. For coverage badge:
   - Sign up at https://codecov.io
   - Replace 'TODO' with your actual token
4. For build status badge:
   - Ensure CI/CD workflow exists at .github/workflows/*.yml
   - Branch must match your default branch (main/master)
