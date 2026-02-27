# Marketplace Readiness: Handoff

This document guides you through preparing your package for submission to the Claude Code plugin marketplace.

## Marketplace Requirements Checklist

### Visual Assets

#### Icon (512x512 PNG)
- **Location**: `.claude-plugin/icon.png`
- **Requirements**:
  - Size: Exactly 512x512 pixels
  - Format: PNG with transparency
  - Content: First letter of package name or relevant symbol

**Generation Commands**:
```bash
# Using ImageMagick (if available)
convert -size 512x512 xc:transparent \
        -font DejaVu-Sans-Bold \
        -pointsize 400 \
        -fill "#4A90E2" \
        -gravity center \
        -annotate +0+0 "H" \
        .claude-plugin/icon.png

# Or create simple placeholder with Python
python -c "from PIL import Image, ImageDraw; img = Image.new('RGBA', (512, 512), (0, 0, 0, 0)); d = ImageDraw.Draw(img); d.text((256, 256), 'H', fill='#4A90E2', anchor='mm'); img.save('.claude-plugin/icon.png')"
```

#### Screenshots (2-5 images)
- **Location**: `.claude-plugin/screenshots/`
- **Requirements**:
  - Format: PNG or JPG
  - Recommended size: 1280x720 or 1920x1080
  - Content: Show your plugin in action
  - Naming: `screenshot-1.png`, `screenshot-2.png`, etc.

**Screenshot Ideas**:
- Main interface or command output
- Before/after comparison
- Integration example
- Configuration setup
- Results visualization

### Publisher Verification

- **Email**: Must match GitHub account email
- **Organization**: Optional (if publishing as organization)
- **Verification**: GitHub may require email confirmation

### Documentation Standards

#### README.md
- [ ] Clear title and description
- [ ] Installation instructions
- [ ] Quick start example
- [ ] Usage examples
- [ ] Configuration reference
- [ ] Troubleshooting section
- [ ] License information

#### plugin.json
- [ ] Valid JSON format
- [ ] Unique package name
- [ ] Version number (semantic versioning)
- [ ] Accurate description (< 100 characters)
- [ ] Author information
- [ ] License field
- [ ] Keywords (max 5)

### MCP Server Standards (if applicable)

If your package provides an MCP server:

#### Server Lifecycle
- [ ] Startup: Server initializes without errors
- [ ] Shutdown: Clean shutdown without orphaned processes
- [ ] Error handling: Graceful degradation on failures
- [ ] Logging: Structured logs for debugging

#### Required Endpoints
- [ ] `tools/list` - List available tools
- [ ] `tools/call` - Execute tool with parameters
- [ ] `resources/list` - List available resources (optional)
- [ ] `resources/subscribe` - Subscribe to resource updates (optional)

#### Tool Implementation
- [ ] Input validation (type checking, required fields)
- [ ] Output formatting (consistent structure)
- [ ] Error handling (meaningful error messages)
- [ ] Idempotency (safe to retry)

### Testing Requirements

- [ ] Unit tests for core functionality
- [ ] Integration tests for MCP endpoints (if applicable)
- [ ] Manual testing checklist completed
- [ ] Edge cases identified and handled
- [ ] Performance tested (response time < 5s)

## Submission Process

1. **Pre-submission Checklist**
   - [ ] All visual assets created and validated
   - [ ] Documentation complete and reviewed
   - [ ] Tests passing with > 80% coverage
   - [ ] MCP server tested (if applicable)
   - [ ] License file included

2. **Create Release**
   ```bash
   git tag -a v{version} -m "Release v{version}"
   git push origin v{version}
   ```

3. **Submit to Marketplace**
   - Visit: https://claude.ai/marketplace/submit
   - Fill in package details
   - Upload visual assets
   - Provide documentation links
   - Submit for review

4. **Review Timeline**
   - Initial review: 1-3 business days
   - Technical review: 3-5 business days
   - Total time: Up to 2 weeks

## Common Rejections

| Issue | Prevention |
|-------|-------------|
| Invalid icon size | Verify 512x512 exactly with `file .claude-plugin/icon.png` |
| Missing screenshots | Include 2-5 screenshots in `.claude-plugin/screenshots/` |
| Broken MCP endpoints | Test all endpoints with sample inputs |
| Incomplete documentation | Use README checklist above |
| License unclear | Include LICENSE file with standard license (MIT/Apache-2.0) |
| Naming conflicts | Search marketplace before choosing package name |

## Verification Checklist

Run this before submission:

```bash
# Check icon size and format
file .claude-plugin/icon.png
# Should output: "PNG image data, 512 x 512"

# Verify plugin.json syntax
python -m json.tool .claude-plugin/plugin.json

# Check MCP server (if applicable)
claude-code-mcp test

# Run tests
pytest tests/ -v --cov

# Verify README has all sections
grep -E "## (Installation|Usage|Configuration|Troubleshooting|License)" README.md
```

**Ready for submission when**: All items checked above pass.

---

*Generated: 2026-02-26*
*Package: handoff*
