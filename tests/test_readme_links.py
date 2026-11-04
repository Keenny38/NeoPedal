"""README pages (front page of the repository): every local image and link points to a file of the
repository, every #anchor to a heading of the page, and the English and French pages stay in step"""

import os
import re
import unicodedata

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = ("README.md", "README.fr.md")
# Markdown links & images, HTML src & href
LINK = re.compile(r"\]\(([^)\s]+)\)|(?:src|href|srcset)=\"([^\"]+)\"")
CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)


def read(name: str) -> str:
    with open(os.path.join(ROOT, name), encoding="utf-8") as file:
        return CODE_BLOCK.sub("", file.read())


def links(text: str) -> list[str]:
    return [markdown or html for markdown, html in LINK.findall(text)]


def anchor(heading: str) -> str:
    """GitHub heading id: lower case, punctuation & emoji dropped (letters, digits, marks of letters kept),
    spaces made hyphens"""
    kept = []
    for char in heading.strip().lower():
        category = unicodedata.category(char)
        if char in " -_" or category[0] in "LN" or (category == "Mn" and kept and kept[-1].isalpha()):
            kept.append(char)
    return "".join(kept).replace(" ", "-")


def anchors(text: str) -> set[str]:
    return {anchor(match) for match in re.findall(r"^#{1,6} (.+)$", text, re.MULTILINE)}


@pytest.mark.parametrize("page", PAGES)
def test_local_links_exist(page):
    missing = []
    for target in links(read(page)):
        if re.match(r"[a-z]+:", target) or target.startswith("#"):
            continue
        path = target.split("#")[0]
        if not os.path.exists(os.path.join(ROOT, path)):
            missing.append(target)
    assert not missing, f"{page}: missing {missing}"


@pytest.mark.parametrize("page", PAGES)
def test_anchors_exist(page):
    text = read(page)
    found = anchors(text)
    broken = [target for target in links(text) if target.startswith("#") and target[1:] not in found]
    assert not broken, f"{page}: no heading for {broken}, headings {sorted(found)}"


def test_pages_in_step():
    """Same pictures in the same order on both pages, each page links the other"""
    english, french = read("README.md"), read("README.fr.md")

    def pictures(text):
        return [target for target in links(text) if target.startswith(("images/", "docs/"))
                and target.endswith((".png", ".gif"))]

    assert pictures(english) == pictures(french)
    assert "README.fr.md" in links(english) and "README.md" in links(french)


def test_anchor_rule():
    assert anchor("🏁 Quick start") == "-quick-start"
    assert anchor("🔒 Sûr à utiliser") == "-sûr-à-utiliser"
    assert anchor("📜 License and credits") == "-license-and-credits"
    assert anchor("Results & Replays") == "results--replays"
