#!/usr/bin/env python3
"""
Generate macOS app icons from source image with squircle mask.
Creates web icons (32, 180, 512) and iconset folder for .icns conversion.
"""

import os
import sys
import math
from pathlib import Path
from PIL import Image, ImageDraw

def create_squircle_mask(size, corner_radius_ratio=0.2237):
    """
    Create a squircle mask image at given size.
    corner_radius_ratio: 22.37% of side (standard macOS)
    Returns an RGBA image with squircle as white on transparent background.
    """
    mask = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(mask)

    # Draw a rounded rectangle as squircle approximation
    corner_radius = int(size * corner_radius_ratio)

    # Draw filled rounded rectangle
    draw.rounded_rectangle(
        [(0, 0), (size - 1, size - 1)],
        radius=corner_radius,
        fill=(255, 255, 255, 255)
    )

    return mask

def apply_squircle_and_margin(source_image, target_size, canvas_size=1024, squircle_size=824):
    """
    Apply squircle mask with margin to source image.
    Works at 4x resolution for smooth edges, then downsamples.
    """
    scale = 4
    scaled_canvas = canvas_size * scale
    scaled_squircle = squircle_size * scale

    # Create 4x resolution canvas
    canvas = Image.new('RGBA', (scaled_canvas, scaled_canvas), (0, 0, 0, 0))

    # Scale and place source image to fill the squircle area
    # Source is 2048x2048, we want to fit it into the squircle
    src_scaled = source_image.resize((scaled_squircle, scaled_squircle), Image.Resampling.LANCZOS)

    # Center the squircle on the canvas
    offset = (scaled_canvas - scaled_squircle) // 2
    canvas.paste(src_scaled, (offset, offset))

    # Squircle mask of the squircle's own size, placed at the same offset as the artwork
    sq = create_squircle_mask(scaled_squircle, corner_radius_ratio=0.2237).split()[3]
    mask = Image.new('L', (scaled_canvas, scaled_canvas), 0)
    mask.paste(sq, (offset, offset))

    # Apply mask
    canvas.putalpha(mask)

    # Downsample to target size for smooth edges
    result = canvas.resize((target_size, target_size), Image.Resampling.LANCZOS)

    return result

def main():
    # Paths
    # исходник: аргумент командной строки или текущая иконка Cutlab (плей-клякса, 28.09)
    source_path = Path(sys.argv[1] if len(sys.argv) > 1 else '/Users/romanroak/NIK/assets/ui/icon/v2/5_play_dark.png')
    web_dir = Path('/Users/romanroak/NIK/studio/editor/web')
    iconset_dir = Path('/Users/romanroak/NIK/assets/ui/icon/icon.iconset')

    # Create directories
    web_dir.mkdir(parents=True, exist_ok=True)
    iconset_dir.mkdir(parents=True, exist_ok=True)

    # Load source image
    print(f"Loading source image: {source_path}")
    source = Image.open(source_path).convert('RGBA')
    print(f"Source size: {source.size}")

    # Generate web icons
    web_sizes = {
        'icon-32.png': 32,
        'icon-180.png': 180,
        'icon-512.png': 512,
    }

    print("\nGenerating web icons...")
    for filename, size in web_sizes.items():
        output_path = web_dir / filename
        icon = apply_squircle_and_margin(source, size)
        icon.save(output_path, 'PNG')
        print(f"  {filename}: {size}x{size} -> {output_path}")

    # Generate iconset for .icns conversion
    iconset_sizes = [
        (16, '16x16'),
        (32, '32x32'),
        (128, '128x128'),
        (256, '256x256'),
        (512, '512x512'),
    ]

    print("\nGenerating iconset...")
    for size, label in iconset_sizes:
        # @1x version
        icon = apply_squircle_and_margin(source, size)
        output_path = iconset_dir / f'icon_{label}.png'
        icon.save(output_path, 'PNG')
        print(f"  icon_{label}.png: {size}x{size}")

        # @2x version (double size)
        icon_2x = apply_squircle_and_margin(source, size * 2)
        output_path_2x = iconset_dir / f'icon_{label}@2x.png'
        icon_2x.save(output_path_2x, 'PNG')
        print(f"  icon_{label}@2x.png: {size*2}x{size*2}")

    print(f"\nIconset created at: {iconset_dir}")
    print("\nNext step: run 'iconutil -c icns' to convert iconset to .icns")

if __name__ == '__main__':
    main()
