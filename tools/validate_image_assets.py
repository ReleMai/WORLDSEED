"""Decode visual assets once each and report actionable file-level errors."""
from pathlib import Path

from PIL import Image, UnidentifiedImageError


def image_issues(paths, *, root: Path | None = None) -> tuple[int, list[str]]:
    root = root or Path.cwd()
    unique = sorted({Path(path).resolve() for path in paths})
    issues = []
    for path in unique:
        try:
            label = str(path.relative_to(root.resolve()))
        except ValueError:
            label = str(path)
        try:
            with Image.open(path) as image:
                image.load()  # IDAT corruption can survive open() and fail only on decode.
                if image.format != 'PNG':
                    issues.append(f'{label}: expected PNG; got {image.format}')
                is_terrain = 'terrain' in {part.lower() for part in path.parts}
                if not is_terrain and image.mode != 'RGBA':
                    issues.append(f'{label}: mode={image.mode}; overlay sprites require RGBA (convert and save as PNG)')
                if image.width < 24 or image.height < 24:
                    issues.append(f'{label}: dimensions={image.width}x{image.height}; minimum is 24x24')
        except (OSError, ValueError, UnidentifiedImageError) as exc:
            issues.append(f'{label}: PNG decode failed ({type(exc).__name__}: {exc}); re-export the source image')
    return len(unique), issues
