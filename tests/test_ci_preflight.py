"""CI preflight & dev lock (release 0.28.0 post-mortem): same tool versions as Checks, Checks before a release"""

import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import check
import ci_preflight


def read(name: str) -> str:
    with open(os.path.join(ROOT, name), encoding="utf-8") as file:
        return file.read()


def pins(text: str) -> dict[str, str]:
    found = {}
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)==([^\s;\\]+)", line)
        if match:
            found[match.group(1).lower().replace("_", "-")] = match.group(2)
    return found


def names(text: str) -> set[str]:
    return {re.split(r"[<>=;\s\[]", line, maxsplit=1)[0].lower().replace("_", "-")
            for line in text.splitlines() if line.strip() and not line.startswith(("#", "-"))}


def run_git(repo, *args) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Repo with one commit, as ROOT of check.py & ci_preflight.py"""
    path = tmp_path / "repo"
    path.mkdir()
    run_git(path, "init", "-q", "-b", "master")
    run_git(path, "config", "user.email", "test@example.com")
    run_git(path, "config", "user.name", "Test")
    run_git(path, "config", "commit.gpgsign", "false")
    (path / ".gitignore").write_text("*.log\n", encoding="utf-8")
    (path / "code.py").write_text("a = 1\n", encoding="utf-8")
    (path / "CHANGELOG.md").write_text("# Changelog\n\n## 0.1.0\n\n- first\n", encoding="utf-8")
    run_git(path, "add", "-A")
    run_git(path, "commit", "-q", "-m", "first")
    monkeypatch.setattr(check, "ROOT", str(path))
    monkeypatch.setattr(ci_preflight, "ROOT", str(path))
    return path


def test_dev_lock_pins_every_requirement_at_release_versions():
    lock = pins(read("requirements-dev-lock.txt"))
    assert names(read("requirements-dev.txt")) <= set(lock)
    assert names(read("requirements.txt")) <= set(lock)
    for name, version in pins(read("requirements-lock.txt")).items():
        assert lock.get(name, version) == version, f"requirements-dev-lock.txt: {name} not {version}, regenerate it"


def test_lock_mismatches_only_for_this_platform(tmp_path):
    from importlib import metadata

    lock = tmp_path / "lock.txt"
    lock.write_text(f"# comment\npytest=={metadata.version('pytest')}\npluggy==0.0.1\n"
                    "colorama==0.0.1 ; sys_platform == 'nowhere'\nnot-a-package-np==1.0\n", encoding="utf-8")
    assert check.lock_mismatches(str(lock)) == [
        f"pluggy {metadata.version('pluggy')} (Checks: 0.0.1)", "not-a-package-np not installed (Checks: 1.0)"]


def test_snapshot_takes_working_tree_without_touching_it(repo):
    (repo / "code.py").write_text("a = 2\n", encoding="utf-8")
    (repo / "new.py").write_text("b = 1\n", encoding="utf-8")
    (repo / "debug.log").write_text("ignored\n", encoding="utf-8")
    run_git(repo, "add", "new.py")  # staged file stays staged
    (repo / "other.py").write_text("c = 1\n", encoding="utf-8")
    head = run_git(repo, "rev-parse", "HEAD")
    status = run_git(repo, "status", "--porcelain")

    sha, untracked = ci_preflight.snapshot()
    assert run_git(repo, "status", "--porcelain") == status
    assert run_git(repo, "rev-parse", "HEAD") == head
    assert run_git(repo, "rev-parse", f"{sha}^") == head
    assert run_git(repo, "show", f"{sha}:code.py") == "a = 2"
    assert set(run_git(repo, "ls-tree", "--name-only", sha).splitlines()) == {
        ".gitignore", "CHANGELOG.md", "code.py", "new.py", "other.py"}
    assert untracked == ["other.py"]  # new.py is in the index already
    assert not os.path.exists(os.path.join(repo, run_git(repo, "rev-parse", "--git-path", "preflight-index")))


def test_doc_only_paths():
    assert ci_preflight.doc_only(["CHANGELOG.md", "CHANGELOG.fr.md", "README.md", "docs/changes/a.png",
                                  "docs/wiki/Home.md", "docs/wiki/sub/page.md"])
    assert ci_preflight.doc_only([])
    assert not ci_preflight.doc_only(["CHANGELOG.md", "neopedal/app.py"])
    assert not ci_preflight.doc_only(["docs/customization.md"])  # option help generated from it


def test_release_push_needs_passed_checks(repo, monkeypatch):
    base = run_git(repo, "rev-parse", "HEAD")
    run_git(repo, "update-ref", "refs/remotes/origin/master", base)
    (repo / "code.py").write_text("a = 3\n", encoding="utf-8")
    run_git(repo, "commit", "-q", "-am", "work")
    monkeypatch.delenv("NEOPEDAL_SKIP_PREFLIGHT", raising=False)
    monkeypatch.setattr(ci_preflight, "passed_base", lambda sha: None)
    assert check.release_without_checks() == ""  # no release section: any push

    with open(repo / "CHANGELOG.md", "a", encoding="utf-8") as file:
        file.write("\n## 0.2.0\n\n- second\n")
    run_git(repo, "commit", "-q", "-am", "Release 0.2.0")
    assert check.new_release_versions(base, "HEAD") == ["0.2.0"]
    assert "0.2.0: Checks never passed" in check.release_without_checks()

    monkeypatch.setattr(ci_preflight, "passed_base", lambda sha: base)
    assert check.release_without_checks() == ""
    monkeypatch.setattr(ci_preflight, "passed_base", lambda sha: None)
    monkeypatch.setenv("NEOPEDAL_SKIP_PREFLIGHT", "1")
    assert check.release_without_checks() == ""

    def offline(sha):
        raise SystemExit("gh: not logged in")

    monkeypatch.delenv("NEOPEDAL_SKIP_PREFLIGHT")
    monkeypatch.setattr(ci_preflight, "passed_base", offline)
    assert "Checks state not read (gh: not logged in)" in check.release_without_checks()


def test_passed_base_accepts_documentation_changes_only(repo, monkeypatch):
    base = run_git(repo, "rev-parse", "HEAD")
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## 0.2.0\n", encoding="utf-8")
    run_git(repo, "commit", "-q", "-am", "doc")
    doc = run_git(repo, "rev-parse", "HEAD")
    (repo / "code.py").write_text("a = 4\n", encoding="utf-8")
    run_git(repo, "commit", "-q", "-am", "code")
    code = run_git(repo, "rev-parse", "HEAD")
    runs = [{"headSha": "0" * 40, "event": "push"}, {"headSha": base, "event": "pull_request"},
            {"headSha": base, "event": "workflow_dispatch"}]
    monkeypatch.setattr(ci_preflight, "gh_json", lambda *args: runs)
    monkeypatch.setattr(ci_preflight, "git", lambda *args, **kwargs: "")  # no fetch of the unknown commit
    assert ci_preflight.passed_base(doc) == base
    assert ci_preflight.passed_base(code) is None


# --- 0.28.0 post-mortem items 4-7 & 16-18: matrix, xdist on Windows, shorter hook, nightly, release pipeline

def workflow(name: str) -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(read(f".github/workflows/{name}"))


def triggers(data: dict) -> dict:
    return data.get("on", data.get(True))  # YAML 1.1 reads the "on" key as True


def test_hook_tests_without_coverage_and_stop_after_20_failures():
    hook = check.test_command(["py"], "auto", coverage=False, maxfail=20)
    assert hook == ["py", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-n", "auto", "--timeout=300",
                    "--maxfail=20"]
    full = check.test_command(["py"], 0)
    assert "-n" not in full and "--cov=neopedal" in full and not any(arg.startswith("--maxfail") for arg in full)
    assert "-x" not in hook and "-x" not in full


def test_checks_spread_tests_on_every_cell_with_coverage_on_3_13_only():
    data = workflow("checks.yml")
    assert data["jobs"]["checks"]["strategy"]["matrix"] == {  # required check names
        "os": ["ubuntu-latest", "windows-latest"], "python-version": ["3.11", "3.13", "3.14"]}
    tests = next(step["run"] for step in data["jobs"]["checks"]["steps"] if step.get("name", "").startswith("Tests"))
    assert "-n auto" in tests and "runner.os" not in tests  # Windows cells too
    assert "matrix.python-version == '3.13' && '--cov=neopedal" in tests


def test_nightly_random_order_workflow():
    data = workflow("nightly.yml")
    assert triggers(data)["schedule"][0]["cron"].split()[2:] == ["*", "*", "*"]  # every night
    assert data["permissions"] == {"contents": "read"}
    assert data["concurrency"]["cancel-in-progress"] is True
    job = data["jobs"]["random-order"]
    assert job["timeout-minutes"] <= 60 and job["strategy"]["fail-fast"] is False
    assert job["strategy"]["matrix"]["run"] == [1, 2, 3]
    assert {(item["os"], item["python-version"]) for item in job["strategy"]["matrix"]["include"]} == {
        ("ubuntu-latest", "3.14"), ("windows-latest", "3.13")}
    runs = "\n".join(step.get("run", "") for step in job["steps"])
    assert "pip install -r requirements-dev-lock.txt" in runs
    assert re.search(r"pytest-randomly==[\d.]+ --hash=sha256:[0-9a-f]{64}", runs)
    assert "--require-hashes --no-deps --only-binary :all:" in runs
    assert "--randomly-seed=" in runs and "Test order seed" in runs and "--cov" not in runs
    for step in job["steps"]:
        if "uses" in step:
            assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", step["uses"])


def test_push_builds_without_publishing():
    data = workflow("build-release.yml")
    assert triggers(data)["push"] == {"branches": ["master"]}
    assert "build_run_id" in triggers(data)["workflow_dispatch"]["inputs"]
    jobs = data["jobs"]
    release = jobs["release"]
    assert "github.event_name == 'workflow_dispatch'" in release["if"] and "!inputs.test_build" in release["if"]
    assert release["environment"] == "release"
    for name in ("linux", "windows"):
        assert "!inputs.build_run_id" in jobs[name]["if"]
    version_steps = {step["name"]: step for step in jobs["version"]["steps"]}
    assert version_steps["Release only from master, after Checks passed"]["if"] == (
        "${{ github.event_name == 'workflow_dispatch' && !inputs.test_build }}")
    check_run = version_steps["Build run of the same commit"]["run"]
    assert 'wanted="$workflow push master $GITHUB_SHA completed success"' in check_run
    assert '"source windows"' in check_run
    downloads = [step for step in release["steps"] if step.get("uses", "").startswith("actions/download-artifact@")]
    assert [step["with"].get("run-id") for step in downloads] == [None, "${{ inputs.build_run_id }}"]
    files = next(step["run"] for step in release["steps"] if step.get("name") == "Check installer files")
    assert 'if [ "$found" != "$expected" ]' in files
    assert "needs.windows.outputs" not in str(release)  # hashes read from the published files


def test_failed_tests_read_from_job_logs():
    log = ("2026-11-01T13:41:45Z [gw1] [  6%] FAILED tests/test_a.py::test_x[alerts-True] \n"
           "2026-11-01T13:41:46Z [gw2] [ 16%] PASSED tests/test_a.py::test_y\n"
           "2026-11-01T13:46:39Z \x1b[31mFAILED\x1b[0m tests/test_b.py::test_z[pit-Modern Dark] - worker 'gw2' crashed\n"
           "2026-11-01T13:46:39Z ERROR tests/test_c.py::test_setup - fixture failed\n"
           "2026-11-01T13:46:39Z ERROR tests/test_d.py - ImportError\n")  # collection error: no test id
    from release import failed_tests

    assert failed_tests(log) == {"tests/test_a.py::test_x[alerts-True]", "tests/test_b.py::test_z[pit-Modern Dark]",
                                 "tests/test_c.py::test_setup"}


def job(name: str, conclusion: str = "failure", step: str = "Tests (coverage on Python 3.13)", job_id: int = 1) -> dict:
    return {"name": name, "conclusion": conclusion, "databaseId": job_id,
            "steps": [{"name": "Lint", "conclusion": "success"}, {"name": step, "conclusion": conclusion}]}


@pytest.fixture
def fake_logs(monkeypatch):
    """Job logs answered from a dict"""
    import release

    logs: dict[int, str] = {}
    monkeypatch.setattr(release, "job_log", lambda job_id: logs.get(job_id, ""))
    return logs


def test_flaky_failures_only_with_runner_flaky_tests(monkeypatch, fake_logs):
    import release

    jobs = [job("checks (ubuntu-latest, 3.11)", job_id=1), job("checks (windows-latest, 3.14)", job_id=2),
            {"name": "visual-regression", "conclusion": "success", "databaseId": 3, "steps": []}]
    monkeypatch.setattr(release, "gh_json", lambda *args: {"jobs": jobs})
    monkeypatch.setattr(release, "flaky_tests", lambda: {"tests/test_a.py::test_slow", "tests/test_b.py::test_t[1]"})
    fake_logs.update({1: "FAILED tests/test_a.py::test_slow - timeout\n", 2: "x FAILED tests/test_b.py::test_t[1]\n"})
    assert release.flaky_failures(10) == (["tests/test_a.py::test_slow", "tests/test_b.py::test_t[1]"], "")

    fake_logs[2] = "FAILED tests/test_b.py::test_t[1]\nFAILED tests/test_b.py::test_real\n"
    tests, why = release.flaky_failures(10)
    assert tests == [] and "not marked runner_flaky: tests/test_b.py::test_real" in why

    fake_logs[2] = "Required test coverage of 88% not reached\n"
    assert "no failed test found" in release.flaky_failures(10)[1]

    jobs[1] = job("checks (windows-latest, 3.14)", step="Lint", job_id=2)
    assert "Lint, not only tests" in release.flaky_failures(10)[1]
    jobs[1] = job("checks (windows-latest, 3.14)", conclusion="cancelled", job_id=2)
    assert release.flaky_failures(10)[0] == []

    jobs[1] = job("checks (windows-latest, 3.14)", job_id=2)
    fake_logs[2] = "FAILED tests/test_b.py::test_t[1]\n"
    monkeypatch.setattr(release, "flaky_tests", lambda: None)
    assert "not collected" in release.flaky_failures(10)[1]


def test_rerun_of_flaky_failures_once(monkeypatch):
    import release

    commands = []
    monkeypatch.setattr(release, "run", lambda *command, **kwargs: commands.append(command) or "")
    monkeypatch.setattr(release, "flaky_failures", lambda run_id: (["tests/test_a.py::test_slow"], ""))
    monkeypatch.setattr(release, "gh_json", lambda *args: {"attempt": 2, "status": "queued"})
    monkeypatch.setattr(release.time, "sleep", lambda seconds: None)
    assert not release.rerun_flaky({"databaseId": 7, "attempt": 2})  # rerun already
    assert commands == []
    assert release.rerun_flaky({"databaseId": 7, "attempt": 1})
    assert commands == [("gh", "run", "rerun", "7", "--failed", "--repo", release.REPO)]

    monkeypatch.setattr(release, "flaky_failures", lambda run_id: ([], "not marked runner_flaky: x"))
    assert not release.rerun_flaky({"databaseId": 8, "attempt": 1})


def test_wait_checks_reruns_flaky_failures_one_time(monkeypatch):
    import release

    states = iter([("failure", ["a"]), ("running", []), ("failure", ["a"])])
    reruns = []
    monkeypatch.setattr(release, "checks_state", lambda sha: next(states))
    monkeypatch.setattr(release, "checks_runs", lambda sha: [{"databaseId": 5, "attempt": 1}])
    monkeypatch.setattr(release, "rerun_flaky", lambda checks_run: reruns.append(checks_run) or True)
    monkeypatch.setattr(release.time, "sleep", lambda seconds: None)
    assert release.wait_checks("a" * 40) == ("failure", ["a"])
    assert len(reruns) == 1  # second failure: no other rerun

    states = iter([("failure", ["a"]), ("success", [])])
    assert release.wait_checks("a" * 40) == ("success", [])
    states = iter([("failure", ["a"])])
    assert release.wait_checks("a" * 40, rerun_flakes=False) == ("failure", ["a"])


def test_release_reuses_passed_push_build(monkeypatch):
    import release

    build = {"databaseId": 42, "status": "completed", "conclusion": "success"}
    artifacts = {"artifacts": [{"name": "source", "expired": False}, {"name": "windows", "expired": False}]}
    monkeypatch.setattr(release, "build_run", lambda sha: build)
    monkeypatch.setattr(release, "gh_json", lambda *args: artifacts)
    monkeypatch.setattr(release, "run", lambda *command, **kwargs: "1.2.0")  # version from commit titles
    assert release.reusable_build("a" * 40, "1.2.0", "auto") == (42, "")
    assert release.reusable_build("a" * 40, "1.2.0", "minor") == (42, "")  # same version anyway
    assert release.reusable_build("a" * 40, "2.0.0", "major")[0] is None

    artifacts["artifacts"][1]["expired"] = True
    assert "built nothing" in release.reusable_build("a" * 40, "1.2.0", "auto")[1]
    build["conclusion"] = "failure"
    assert "failure" in release.reusable_build("a" * 40, "1.2.0", "auto")[1]
    monkeypatch.setattr(release, "build_run", lambda sha: None)
    assert release.reusable_build("a" * 40, "1.2.0", "auto") == (None, "no build started by the push of this commit")


def test_release_run_publishes_build_run_files(monkeypatch):
    import release

    commands = []
    monkeypatch.setattr(release, "run", lambda *command, **kwargs: commands.append(command) or "")
    runs = iter([[], [{"databaseId": 9, "event": "workflow_dispatch"}]])
    monkeypatch.setattr(release, "gh_json", lambda *args: next(runs))
    monkeypatch.setattr(release.time, "sleep", lambda seconds: None)
    assert release.start_release("auto", 42) == 9
    assert commands == [("gh", "workflow", "run", release.WORKFLOW, "--repo", release.REPO, "--ref", "master",
                         "-f", "bump=auto", "-f", "build_run_id=42")]


def test_release_commit_takes_the_tested_snapshot(repo, monkeypatch):
    import release

    monkeypatch.setattr(release, "ROOT", str(repo))
    (repo / "code.py").write_text("a = 5\n", encoding="utf-8")
    (repo / "new.py").write_text("b = 2\n", encoding="utf-8")
    head = run_git(repo, "rev-parse", "HEAD")
    snapshot, _ = ci_preflight.snapshot()
    (repo / "code.py").write_text("a = 6\n", encoding="utf-8")  # changed after the preflight: not tested

    sha = release.write_release_commit(snapshot, ["Release 0.2.0", "Body"])
    assert run_git(repo, "rev-parse", "HEAD") == sha and run_git(repo, "rev-parse", f"{sha}^") == head
    assert run_git(repo, "rev-parse", f"{sha}^{{tree}}") == run_git(repo, "rev-parse", f"{snapshot}^{{tree}}")
    assert run_git(repo, "log", "-1", "--format=%B", sha).strip() == "Release 0.2.0\n\nBody"
    assert run_git(repo, "show", "HEAD:new.py") == "b = 2"
    assert (repo / "code.py").read_text(encoding="utf-8") == "a = 6\n"  # working tree kept
    assert run_git(repo, "status", "--porcelain") == "M code.py"  # index = the commit
    assert release.write_release_commit(snapshot, ["Again"]) == ""  # HEAD moved since the snapshot

    assert release.changelogs_without("0.1.0") == ["CHANGELOG.fr.md"]
    assert release.changelogs_without("0.3.0") == ["CHANGELOG.md", "CHANGELOG.fr.md"]


def test_matrix_tree_copy_keeps_executable_bits_without_ignored_files(repo, tmp_path):
    import io
    import tarfile

    (repo / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    run_git(repo, "add", "run.sh")
    run_git(repo, "update-index", "--chmod=+x", "run.sh")
    (repo / "new.py").write_text("b = 1\n", encoding="utf-8")
    (repo / "debug.log").write_text("ignored\n", encoding="utf-8")
    (repo / "code.py").unlink()  # deleted: not copied
    assert dict(check.tree_files()) == {".gitignore": False, "CHANGELOG.md": False, "run.sh": True, "new.py": False}

    with tarfile.open(fileobj=io.BytesIO(check.tree_tar())) as tar:
        modes = {member.name: member.mode for member in tar.getmembers()}
    assert modes == {".gitignore": 0o644, "CHANGELOG.md": 0o644, "run.sh": 0o755, "new.py": 0o644}

    target = tmp_path / "copy"
    (target / "stale").mkdir(parents=True)
    check.copy_tree(str(target))
    assert sorted(path.name for path in target.iterdir()) == [".git", ".gitignore", "CHANGELOG.md", "new.py", "run.sh"]
    assert run_git(target, "status", "--porcelain") == ""  # committed in a repo of its own, like a CI checkout
    assert run_git(target, "ls-files", "-s", "run.sh").startswith("100755 ")


def test_matrix_skips_missing_environments_with_setup(repo, monkeypatch):
    monkeypatch.setattr(check, "wsl_command", lambda: (None, "WSL not installed or no Linux distribution"))
    runs, skipped = check.matrix_runs()
    assert len(runs) == 1 and runs[0].cwd == str(repo)
    assert any("uv venv --python 3.11 .venv311" in reason for reason in skipped)
    assert any(reason.startswith("Linux Python 3.14 (WSL): WSL not installed") for reason in skipped)

    scripts = repo / ".venv311" / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "python.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(check, "wsl_command", lambda: (["wsl.exe", "--exec", "sh", "-c"], ""))
    runs, skipped = check.matrix_runs()
    assert skipped == [] and len(runs) == 3
    py311, linux = runs[1], runs[2]
    assert py311.python == [str(scripts / "python.exe")] and py311.cwd != str(repo)  # on a copy
    assert {run.env.get(check.PORT_OFFSET_ENV) for run in runs[:2]} == {"0", "1000"}
    linux.set_test_args(check.test_command([], 4, coverage=False))
    assert linux.command[:4] == ["wsl.exe", "--exec", "sh", "-c"]
    assert f"{check.PORT_OFFSET_ENV}=2000" in linux.command[4] and linux.command[4].endswith(
        "bin/python -m pytest -q -p no:cacheprovider -n 4 --timeout=300")


def test_matrix_windows_runs_wait_for_port_isolation(repo, monkeypatch):
    tests = repo / "tests"
    tests.mkdir()
    for name in ("test_command_server.py", "test_web_dashboard.py"):
        (tests / name).write_text('PORT = 18337 + 10 * worker\n', encoding="utf-8")
    assert not check.ports_isolated()
    for name in ("test_command_server.py", "test_web_dashboard.py"):
        (tests / name).write_text(f'PORT = 18337 + int(os.environ.get("{check.PORT_OFFSET_ENV}", "0"))\n',
                                  encoding="utf-8")
    assert check.ports_isolated()
