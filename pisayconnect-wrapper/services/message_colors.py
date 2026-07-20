"""Remap inline HTML colors to Catppuccin CSS variables."""

import re
from functools import lru_cache

from bs4 import BeautifulSoup

COLOR_ATTRS = ("color", "background-color", "background", "border-color")

CATPPUCCIN_COLORS = {
    "rosewater": (220, 138, 120),
    "flamingo": (221, 120, 120),
    "pink": (234, 118, 203),
    "mauve": (136, 57, 239),
    "red": (210, 15, 57),
    "maroon": (230, 69, 83),
    "peach": (254, 100, 11),
    "yellow": (223, 142, 29),
    "green": (64, 160, 43),
    "teal": (23, 146, 153),
    "sky": (4, 165, 229),
    "sapphire": (32, 159, 181),
    "blue": (30, 102, 245),
    "lavender": (114, 135, 253),
    "text": (76, 79, 105),
    "subtext1": (92, 95, 119),
    "subtext0": (108, 111, 133),
    "overlay2": (124, 127, 147),
    "overlay1": (140, 143, 161),
    "overlay0": (156, 160, 176),
    "surface2": (172, 176, 190),
    "surface1": (188, 192, 204),
    "surface0": (204, 208, 218),
    "base": (239, 241, 245),
    "mantle": (230, 233, 239),
    "crust": (220, 224, 232),
}

HEX_COLOR_RE = re.compile(
    r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b"
)
RGB_COLOR_RE = re.compile(
    r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*[\d.]+)?\s*\)",
    re.IGNORECASE,
)
NAMED_COLORS = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "red": (255, 0, 0),
    "green": (0, 128, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "orange": (255, 165, 0),
    "purple": (128, 0, 128),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
}


def _expand_hex(hex_value):
    value = hex_value.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) == 8:
        value = value[:6]
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _parse_color(value):
    if not value:
        return None

    cleaned = value.strip().lower()
    if cleaned in NAMED_COLORS:
        return NAMED_COLORS[cleaned]

    if cleaned.startswith("#"):
        try:
            return _expand_hex(cleaned)
        except ValueError:
            return None

    rgb_match = RGB_COLOR_RE.match(cleaned)
    if rgb_match:
        return tuple(int(rgb_match.group(i)) for i in range(1, 4))

    return None


@lru_cache(maxsize=512)
def closest_palette_name(rgb):
    best_name = "text"
    best_distance = float("inf")

    for name, palette_rgb in CATPPUCCIN_COLORS.items():
        distance = sum((a - b) ** 2 for a, b in zip(rgb, palette_rgb))
        if distance < best_distance:
            best_distance = distance
            best_name = name

    return best_name


def remap_color_value(value):
    rgb = _parse_color(value)
    if rgb is None:
        return value
    return f"var(--ctp-{closest_palette_name(rgb)})"


def _remap_style_declarations(style):
    if not style:
        return style

    parts = []
    for declaration in style.split(";"):
        if not declaration.strip():
            continue

        if ":" not in declaration:
            parts.append(declaration.strip())
            continue

        prop, raw_value = declaration.split(":", 1)
        prop = prop.strip().lower()
        value = raw_value.strip()

        if prop in COLOR_ATTRS:
            hex_match = HEX_COLOR_RE.search(value)
            if hex_match:
                remapped = remap_color_value(hex_match.group(0))
                value = HEX_COLOR_RE.sub(remapped, value, count=1)
            else:
                rgb_match = RGB_COLOR_RE.search(value)
                if rgb_match:
                    remapped = remap_color_value(rgb_match.group(0))
                    value = RGB_COLOR_RE.sub(remapped, value, count=1)
                elif value.lower() in NAMED_COLORS:
                    value = remap_color_value(value)

        parts.append(f"{prop}: {value}")

    return "; ".join(parts)


def remap_message_colors(html):
    if not html:
        return html

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(True):
        style = tag.get("style")
        if style:
            tag["style"] = _remap_style_declarations(style)

        if tag.has_attr("color"):
            remapped = remap_color_value(tag["color"])
            if remapped != tag["color"]:
                tag["color"] = remapped

        if tag.has_attr("bgcolor"):
            remapped = remap_color_value(tag["bgcolor"])
            if remapped != tag["bgcolor"]:
                tag["bgcolor"] = remapped

    return str(soup)
