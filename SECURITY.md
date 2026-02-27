# Security Policy

## Supported Versions

Currently, only the latest version of handoff is supported.

## Reporting a Vulnerability

If you discover a security vulnerability, please **do not open a public issue**. Instead, send an email to: security@username.github

Please include:
- Description of the vulnerability
- Steps to reproduce
- Affected versions
- Potential impact

We will respond within 48 hours and provide regular updates.

## Security Best Practices

### For Users

- **Dependencies**: Keep dependencies updated
- **Environment**: Use virtual environments
- **API Keys**: Never commit API keys to repositories

### Known Security Considerations

1. **Dependencies**: All dependencies are from PyPI
2. **File Access**: Tool only reads files from specified paths
3. **Network**: Network operations are documented and transparent

## Security Updates

Security updates will be:
- Announced in release notes
- Published as patch versions
- Available via `pip install --upgrade handoff`

---

Copyright (c) 2026 handoff contributors
