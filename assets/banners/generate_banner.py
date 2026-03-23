#!/usr/bin/env python3
"""Generate professional banner for handoff package."""

from PIL import Image, ImageDraw, ImageFont
import os

# Banner dimensions (GitHub social preview standard)
WIDTH, HEIGHT = 1200, 630

# Colors (professional gradient: dark blue to purple)
COLOR_START = (30, 58, 138)  # Dark blue
COLOR_END = (88, 28, 135)  # Purple
TEXT_COLOR = (255, 255, 255)  # White
ACCENT_COLOR = (147, 51, 234)  # Light purple accent


def create_gradient_background(width, height, color_start, color_end):
    """Create vertical gradient background."""
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)

    for y in range(height):
        ratio = y / height
        r = int(color_start[0] * (1 - ratio) + color_end[0] * ratio)
        g = int(color_start[1] * (1 - ratio) + color_end[1] * ratio)
        b = int(color_start[2] * (1 - ratio) + color_end[2] * ratio)
        draw.rectangle([(0, y), (width, y + 1)], fill=(r, g, b))

    return image


def main():
    # Create gradient background
    img = create_gradient_background(WIDTH, HEIGHT, COLOR_START, COLOR_END)
    draw = ImageDraw.Draw(img)

    # Try to use nice fonts, fall back to default if not available
    try:
        title_font = ImageFont.truetype("Arial", 80)
        subtitle_font = ImageFont.truetype("Arial", 40)
        tag_font = ImageFont.truetype("Arial", 28)
    except:
        title_font = ImageFont.load_default()
        subtitle_font = ImageFont.load_default()
        tag_font = ImageFont.load_default()

    # Draw accent line
    draw.rectangle([(100, 150), (1100, 160)], fill=ACCENT_COLOR)

    # Draw title
    title = "handoff"
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_width = title_bbox[2] - title_bbox[0]
    title_x = (WIDTH - title_width) // 2
    draw.text((title_x, 200), title, fill=TEXT_COLOR, font=title_font)

    # Draw subtitle
    subtitle = "Session Handoff System for Claude Code"
    subtitle_bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
    subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]
    subtitle_x = (WIDTH - subtitle_width) // 2
    draw.text((subtitle_x, 320), subtitle, fill=(200, 200, 255), font=subtitle_font)

    # Draw tags at bottom
    tag1 = "✓ Multi-terminal isolation"
    tag2 = "✓ SHA-256 checksums"
    tag3 = "✓ Auto-save/restore"

    tag_y = 480
    tag_spacing = 400

    tag1_bbox = draw.textbbox((0, 0), tag1, font=tag_font)
    tag1_width = tag1_bbox[2] - tag1_bbox[0]
    draw.text(
        ((WIDTH - tag1_width) // 2, tag_y), tag1, fill=(180, 180, 220), font=tag_font
    )

    tag2_bbox = draw.textbbox((0, 0), tag2, font=tag_font)
    tag2_width = tag2_bbox[2] - tag2_bbox[0]
    draw.text(
        ((WIDTH - tag2_width) // 2, tag_y + 40),
        tag2,
        fill=(180, 180, 220),
        font=tag_font,
    )

    tag3_bbox = draw.textbbox((0, 0), tag3, font=tag_font)
    tag3_width = tag3_bbox[2] - tag3_bbox[0]
    draw.text(
        ((WIDTH - tag3_width) // 2, tag_y + 80),
        tag3,
        fill=(180, 180, 220),
        font=tag_font,
    )

    # Save banner
    output_path = os.path.join(os.path.dirname(__file__), "handoff_banner.png")
    img.save(output_path, "PNG", optimize=True)
    print(f"Banner saved to: {output_path}")
    print(f"Dimensions: {WIDTH}x{HEIGHT}")


if __name__ == "__main__":
    main()
