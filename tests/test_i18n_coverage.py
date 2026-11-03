"""French translation coverage & typography (translation audit 2026-11-01)"""

import ast
import json
import os
import re

from neopedal.i18n.fr import TRANSLATION
from neopedal.i18n.fr_messages import MESSAGE_RULES
from neopedal.i18n.fr_overlay import OVERLAY_LABELS

PACKAGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "neopedal")
DATA = os.path.join(PACKAGE, "i18n", "data")
# Same word in French: no entry needed (English text shown)
SAME_IN_FRENCH = frozenset(("OK",))
_qml_tr = re.compile(r"""i18n\.tr\(\s*"((?:[^"\\]|\\.)*)"\s*[,)]""")


def literal_keys() -> dict[str, list[str]]:
    """English texts given as literal to tr() (Python, tr_overlay aliases left out) & i18n.tr() (QML, comments
    left out): text -> places"""
    keys: dict[str, list[str]] = {}
    for folder, _, files in os.walk(PACKAGE):
        if os.path.basename(folder) == "i18n" or "__pycache__" in folder:
            continue
        for name in files:
            path = os.path.join(folder, name)
            if name.endswith(".py"):
                with open(path, encoding="utf-8") as file:
                    source = file.read()
                if "tr_overlay as tr" in source:
                    continue
                for node in ast.walk(ast.parse(source)):
                    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr"
                            and node.args and isinstance(node.args[0], ast.Constant)
                            and isinstance(node.args[0].value, str)):
                        keys.setdefault(node.args[0].value, []).append(f"{name}:{node.lineno}")
            elif name.endswith(".qml"):
                with open(path, encoding="utf-8") as file:
                    lines = file.read().splitlines()
                for number, line in enumerate(lines, 1):
                    if line.lstrip().startswith("//"):
                        continue
                    for match in _qml_tr.finditer(line.split(" //")[0]):
                        text = match[1].encode().decode("unicode_escape").encode("latin-1").decode("utf-8")
                        keys.setdefault(text, []).append(f"{name}:{number}")
    return keys


def test_literal_texts_translated():
    """Every literal text of tr() / i18n.tr() has a French entry (no English left on French pages)"""
    keys = literal_keys()
    assert len(keys) > 2000  # scan found the texts
    missing = {text: places[:3] for text, places in keys.items()
               if text not in TRANSLATION and text not in SAME_IN_FRENCH}
    assert not missing


def french_values() -> list[tuple[str, str]]:
    """(source, French text) of every translation table"""
    values = [("fr.py", text) for text in TRANSLATION.values()]
    values += [("fr_overlay.py", text) for text in OVERLAY_LABELS.values()]
    values += [("fr_messages.py", text) for _, text in MESSAGE_RULES if isinstance(text, str)]
    for filename in ("fr_options.json", "fr_option_help.json"):
        with open(os.path.join(DATA, filename), encoding="utf-8") as file:
            values += [(filename, text) for text in json.load(file).values()]
    return values


def test_french_typography():
    """No-break space before : ; ! ? and inside « » (never a lone sign starting a wrapped line), … for ellipsis"""
    wrong = [(source, text[:80]) for source, text in french_values()
             if re.search(r" [:;!?](\s|$)", text) or "« " in text or " »" in text or "..." in text]
    assert not wrong
    # Callable replacements (lambda match: f"..."): their f-strings in the source
    with open(os.path.join(PACKAGE, "i18n", "fr_messages.py"), encoding="utf-8") as file:
        lines = [line.strip() for line in file if 'f"' in line and re.search(r' [:;!?]["\s]', line)]
    assert not lines
