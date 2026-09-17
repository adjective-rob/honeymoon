"""Inline SVG icon set for generated reports.

Icon geometry is taken from Lucide (https://lucide.dev, ISC licensed) — the same
library the dashboard uses via ``lucide-react`` — so HTML reports, the SSP, and
the live dashboard all draw the same glyphs.

Reports are self-contained single files, so icons are inlined as SVG markup
rather than loaded from a package. Every icon uses the Lucide contract: a 24x24
viewBox, ``fill="none"``, 2px stroke, round caps and joins.
"""

from __future__ import annotations

# Lucide path geometry, keyed by the upstream icon name.
LUCIDE_PATHS: dict[str, str] = {
    "arrow-right": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "circle": '<circle cx="12" cy="12" r="10"/>',
    "circle-alert": (
        '<circle cx="12" cy="12" r="10"/>'
        '<line x1="12" x2="12" y1="8" y2="12"/>'
        '<line x1="12" x2="12.01" y1="16" y2="16"/>'
    ),
    "circle-check": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "circle-minus": '<circle cx="12" cy="12" r="10"/><path d="M8 12h8"/>',
    "circle-x": (
        '<circle cx="12" cy="12" r="10"/>'
        '<path d="m15 9-6 6"/>'
        '<path d="m9 9 6 6"/>'
    ),
    "hexagon": (
        '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 '
        '1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>'
    ),
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "octagon-alert": (
        '<path d="M12 16h.01"/><path d="M12 8v4"/>'
        '<path d="M15.312 2a2 2 0 0 1 1.414.586l4.688 4.688A2 2 0 0 1 22 8.688v6.624a2 2 0 0 '
        '1-.586 1.414l-4.688 4.688a2 2 0 0 1-1.414.586H8.688a2 2 0 0 1-1.414-.586l-4.688-4.688A2 '
        '2 0 0 1 2 15.312V8.688a2 2 0 0 1 .586-1.414l4.688-4.688A2 2 0 0 1 8.688 2z"/>'
    ),
    "shield-check": (
        '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 '
        '1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>'
        '<path d="m9 12 2 2 4-4"/>'
    ),
    "triangle-alert": (
        '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/>'
        '<path d="M12 9v4"/><path d="M12 17h.01"/>'
    ),
}

# Semantic aliases — what a report means, mapped to the Lucide glyph that says it.
SEVERITY_ICONS: dict[str, str] = {
    "critical": "octagon-alert",
    "high": "triangle-alert",
    "medium": "circle-alert",
    "low": "info",
    "info": "circle",
}

VERDICT_ICONS: dict[str, str] = {
    "confirmed": "circle-check",
    "partial": "circle-alert",
    "disputed": "circle-x",
}

STATUS_ICONS: dict[str, str] = {
    "implemented": "circle-check",
    "partial": "circle-alert",
    "planned": "circle-minus",
}

# Severity/status stroke colors, shared by every report surface.
SEVERITY_COLORS: dict[str, str] = {
    "critical": "#ef4444",
    "high": "#f97316",
    "medium": "#eab308",
    "low": "#3b82f6",
    "info": "#6b7280",
}

VERDICT_COLORS: dict[str, str] = {
    "confirmed": "#10b981",
    "partial": "#eab308",
    "disputed": "#ef4444",
}

STATUS_COLORS: dict[str, str] = {
    "implemented": "#10b981",
    "partial": "#eab308",
    "planned": "#6b7280",
}


def icon_svg(
    name: str,
    size: int = 16,
    color: str = "currentColor",
    extra_attrs: str = "",
) -> str:
    """Render a Lucide icon as inline SVG markup.

    Args:
        name: Lucide icon name (see ``LUCIDE_PATHS``). Unknown names fall back to ``circle``.
        size: Rendered width/height in pixels. Geometry always uses the 24x24 viewBox.
        color: Stroke color. Defaults to ``currentColor`` so icons inherit text color.
        extra_attrs: Additional attributes appended to the ``<svg>`` tag.
    """
    paths = LUCIDE_PATHS.get(name, LUCIDE_PATHS["circle"])
    attrs = f" {extra_attrs}" if extra_attrs else ""
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none"'
        f' stroke="{color}" stroke-width="2" stroke-linecap="round"'
        f' stroke-linejoin="round"{attrs}>{paths}</svg>'
    )


def severity_icon_svg(severity: str, size: int = 14) -> str:
    """Inline SVG icon for a finding severity, colored by severity."""
    key = severity.lower()
    name = SEVERITY_ICONS.get(key, SEVERITY_ICONS["info"])
    color = SEVERITY_COLORS.get(key, SEVERITY_COLORS["info"])
    return icon_svg(name, size=size, color=color)


def verdict_icon_svg(verdict: str, size: int = 20) -> str:
    """Inline SVG icon for a verification verdict, colored by verdict."""
    key = verdict.lower()
    name = VERDICT_ICONS.get(key, VERDICT_ICONS["partial"])
    color = VERDICT_COLORS.get(key, VERDICT_COLORS["partial"])
    return icon_svg(name, size=size, color=color)


def status_icon_svg(status: str, size: int = 16) -> str:
    """Inline SVG icon for an SSP control implementation status."""
    key = status.lower()
    name = STATUS_ICONS.get(key, STATUS_ICONS["planned"])
    color = STATUS_COLORS.get(key, STATUS_COLORS["planned"])
    return icon_svg(name, size=size, color=color)


# Text labels for Markdown reports, where inline SVG does not render.
SEVERITY_LABELS: dict[str, str] = {
    "CRITICAL": "[CRITICAL]",
    "HIGH": "[HIGH]",
    "MEDIUM": "[MEDIUM]",
    "LOW": "[LOW]",
    "INFO": "[INFO]",
}

VERDICT_LABELS: dict[str, str] = {
    "confirmed": "[CONFIRMED]",
    "partial": "[PARTIAL]",
    "disputed": "[DISPUTED]",
}
