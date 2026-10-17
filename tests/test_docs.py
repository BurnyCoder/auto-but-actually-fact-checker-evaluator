"""Tests for the documentation: every local image that README.md embeds exists in the repository.

Global context: the README screenshots are produced by docs/scripts/take_screenshots.py; a renamed or missing PNG
would show up on GitHub as a broken image, so this guards the link targets. Markdown image syntax
`![alt](path)`: https://github.github.com/gfm/#images
"""

import re

from auto_fact_checker.config import ROOT


def test_readme_images_exist():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    images = re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", readme)  # the (path) part of every ![alt](path)
    local = [p for p in images if not p.startswith("http")]  # remote badges/images are not checked offline
    assert local, "README.md should embed the UI screenshots"
    assert [p for p in local if not (ROOT / p).is_file()] == []
