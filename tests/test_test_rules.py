"""Rules of the test suite itself (post-mortem 0.28.0, P1 #8 & #9), read from the source of tests/

- monkeypatch.undo() in a test also undoes the patches of its fixtures (ui_env's Setting.save, the offline
  fixtures) for the rest of the test, and on pytest 9.2 an undo that fails part way leaves the others in place
  for the whole process. Patches meant for part of a test: `with monkeypatch.context() as patch:`. Sites written
  before the rule are counted (ratchet: the count may only go down).
- An instance whose __dict__ is cleared (overlay unloaded) is never monkeypatched in the same test: undo then
  delattrs a missing attribute and stops (0.28.0, 17 to 26 failures per CI cell). Assign the attribute instead.
- A test failing on CI runners only is marked runner_flaky (reruns on CI) and listed in tests/FLAKY.md, never
  skipped there (a skipped test hides a real bug: the 6 menu & focus tests skipped on Windows runners were the
  app with Windows animation effects off).
"""

import ast
import os
import re
from functools import cache

TESTS = os.path.dirname(os.path.abspath(__file__))

# monkeypatch.undo() sites written before the rule (file: count). Lower a count when a site goes, never add one.
UNDO_SITES = {
    "test_audit_h_a4.py": 2,
    "test_audit_i_adapter.py": 2,
    "test_audit_i_h.py": 1,
    "test_audit_recorder_replay_fixes.py": 1,
    "test_bug_audit_2026_11_01.py": 1,
    "test_driver_stats_background.py": 1,
    "test_game_info.py": 2,
    "test_json_setting.py": 3,
    "test_lap_viewer_audit.py": 1,
    "test_lap_viewer_fix_io.py": 1,
    "test_lap_viewer_fix_map.py": 1,
    "test_overlay_audit_2026_10_29_A.py": 2,
    "test_perf_saving_waits.py": 1,
    "test_track_map_official.py": 1,
    "test_ui_audit_2026_10_29_foundations.py": 1,
    "test_ui_audit_2026_10_29_telemetry_notes.py": 1,
    "test_userfile_process.py": 2,
}


@cache
def source_trees() -> dict[str, ast.Module]:
    trees = {}
    for name in sorted(os.listdir(TESTS)):
        if name.endswith(".py"):
            with open(os.path.join(TESTS, name), encoding="utf-8") as file:
                trees[name] = ast.parse(file.read(), name)
    return trees


def calls(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            yield node


def is_monkeypatch(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id == "monkeypatch"


def test_no_new_monkeypatch_undo():
    found = {}
    for name, tree in source_trees().items():
        count = sum(1 for call in calls(tree) if call.func.attr == "undo" and is_monkeypatch(call.func.value))
        if count:
            found[name] = count
    added = {name: count for name, count in found.items() if count > UNDO_SITES.get(name, 0)}
    assert not added, f"monkeypatch.undo() added (use `with monkeypatch.context() as patch:`): {added}"
    gone = {name: found.get(name, 0) for name, count in UNDO_SITES.items() if found.get(name, 0) < count}
    assert not gone, f"monkeypatch.undo() sites removed: lower UNDO_SITES to {gone}"


def test_cleared_instance_never_monkeypatched():
    """`x.__dict__.clear()` and `monkeypatch.setattr(x, ...)` never in the same test function"""
    mixed = []
    for name, tree in source_trees().items():
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            cleared = {ast.unparse(call.func.value.value) for call in calls(function)
                       if call.func.attr == "clear" and isinstance(call.func.value, ast.Attribute)
                       and call.func.value.attr == "__dict__"}
            patched = {ast.unparse(call.args[0]) for call in calls(function)
                       if call.func.attr in ("setattr", "delattr") and is_monkeypatch(call.func.value) and call.args}
            mixed += [f"{name}::{function.name} ({target})" for target in sorted(cleared & patched)]
    assert not mixed, f"instance monkeypatched then its __dict__ cleared (assign instead): {mixed}"


def runner_flaky_tests(tree: ast.Module) -> list[str]:
    names = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                if isinstance(target, ast.Attribute) and target.attr == "runner_flaky":
                    names.append(node.name)
    return names


def test_runner_flaky_tests_listed():
    with open(os.path.join(TESTS, "FLAKY.md"), encoding="utf-8") as file:
        listed = file.read()
    missing = [f"{name}::{test}" for name, tree in source_trees().items() for test in runner_flaky_tests(tree)
               if f"`{test}" not in listed]
    assert not missing, f"runner_flaky tests not listed in tests/FLAKY.md: {missing}"


def test_no_skip_on_ci_runners():
    """A test failing on runners only is marked runner_flaky, not skipped when CI is set"""
    pattern = re.compile(r"""GITHUB_ACTIONS|environ(\.get\(|\[)["']CI["']""")
    found = []
    for name in sorted(os.listdir(TESTS)):
        if name.endswith(".py") and name not in ("conftest.py", os.path.basename(__file__)):
            with open(os.path.join(TESTS, name), encoding="utf-8") as file:
                found += [f"{name}:{number}" for number, line in enumerate(file, 1) if pattern.search(line)]
    assert not found, f"test behaviour depends on the CI environment (use runner_flaky): {found}"
