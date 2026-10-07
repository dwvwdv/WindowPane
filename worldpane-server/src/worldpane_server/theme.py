"""Offbeat theme for the server's web pages (``/dashboard``, ``/demo``).

``static/offbeat.css`` is the single source of the pages' colors: Nord hex values live only
there and the pages use its semantic tokens. Each page's ``<style>`` starts with the
``OFFBEAT_PLACEHOLDER`` comment, replaced here with the stylesheet, so every page (including
the standalone demo file) stays one self-contained HTML document. See docs/ui-conventions.md.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

OFFBEAT_PLACEHOLDER = "/*__OFFBEAT_CSS__*/"


@lru_cache(maxsize=1)
def offbeat_css() -> str:
    return resources.files("worldpane_server").joinpath("static/offbeat.css").read_text(encoding="utf-8")


def with_offbeat(page: str) -> str:
    """``page`` with the Offbeat stylesheet inlined at its placeholder."""
    if OFFBEAT_PLACEHOLDER not in page:
        raise ValueError("page has no Offbeat placeholder in its <style>")
    return page.replace(OFFBEAT_PLACEHOLDER, offbeat_css(), 1)
