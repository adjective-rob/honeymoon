"""Tests for the shared Lucide icon set used by generated reports."""

import re

from honeymoon.icons import (
    LUCIDE_PATHS,
    SEVERITY_ICONS,
    STATUS_ICONS,
    VERDICT_ICONS,
    icon_svg,
    severity_icon_svg,
    status_icon_svg,
    verdict_icon_svg,
)

EMOJI = re.compile(r"[\U0001F300-\U0001FAFF←-➿⬀-⯿️]")


def test_icon_svg_uses_lucide_contract():
    svg = icon_svg("circle-check", size=16, color="#10b981")
    assert 'viewBox="0 0 24 24"' in svg
    assert 'fill="none"' in svg
    assert 'stroke="#10b981"' in svg
    assert 'stroke-width="2"' in svg
    assert 'stroke-linecap="round"' in svg
    assert svg.startswith("<svg") and svg.endswith("</svg>")


def test_icon_svg_defaults_to_current_color():
    assert 'stroke="currentColor"' in icon_svg("check")


def test_unknown_icon_falls_back_to_circle():
    assert LUCIDE_PATHS["circle"] in icon_svg("not-a-real-icon")


def test_extra_attrs_are_appended():
    assert 'style="margin-top:3px"' in icon_svg("arrow-right", extra_attrs='style="margin-top:3px"')


def test_semantic_maps_reference_known_icons():
    for mapping in (SEVERITY_ICONS, VERDICT_ICONS, STATUS_ICONS):
        for name in mapping.values():
            assert name in LUCIDE_PATHS


def test_severity_icons_are_distinct_and_colored():
    critical = severity_icon_svg("critical")
    info = severity_icon_svg("info")
    assert critical != info
    assert 'stroke="#ef4444"' in critical


def test_verdict_and_status_icons_render():
    assert 'stroke="#10b981"' in verdict_icon_svg("confirmed")
    assert 'stroke="#ef4444"' in verdict_icon_svg("disputed")
    assert 'stroke="#10b981"' in status_icon_svg("implemented")
    # Unknown values fall back rather than raising.
    assert verdict_icon_svg("unverified").startswith("<svg")
    assert status_icon_svg("unknown").startswith("<svg")


def test_no_emoji_in_icon_output():
    for name in LUCIDE_PATHS:
        assert not EMOJI.search(icon_svg(name))
