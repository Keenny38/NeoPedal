"""
Publish a release of master: one command, checked before and after

Refuses when master has local changes not pushed, nothing to release, a changelog without the version
section, or Checks not passed on the master commit (waits while they run). Then starts the
"Build and Release" workflow, follows it, and checks the published files (installer .exe, its .sha256,
setup ZIP, source ZIP: every app updater finds its installer; signed manifest: apps since 0.28 require it).

Checks failed only on tests marked runner_flaky (slow shared runners, pytest -m runner_flaky): their failed jobs
are run again once ("gh run rerun --failed"), then the release goes on if they pass.
Build while Checks run: the push of a release commit to master already builds the files (build-release.yml,
push build, nothing published); once Checks and that build passed, the release run publishes its files
(build_run_id) instead of building them again. Without a passed push build, the release run builds them.

Usage (from project root, GitHub CLI logged in):
    python tools/release.py               publish next version (asks before publishing)
    python tools/release.py --dry-run     only check, publish nothing
    python tools/release.py --yes         no question
    python tools/release.py --bump minor  version bump other than from commit titles
    python tools/release.py --preflight   Checks on the working tree first (tools/ci_preflight.py), wait, report,
                                          then offer to write the release commit (-m "title" -m "body" to give
                                          its message), to push before publishing with python tools/release.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "Keenny38/NeoPedal"
WORKFLOW = "build-release.yml"
BUILD_ARTIFACTS = ("source", "windows")  # artifacts of a build run (build-release.yml linux & windows jobs)
# Marker of tests known to fail now and then on shared runners only (tests/conftest.py): a Checks run failed on
# them alone is run again once
FLAKY_MARKER = "runner_flaky"
# Failed test in a job log: "[gw1] [ 6%] FAILED tests/x.py::test[id]" or "FAILED tests/x.py::test[id] - reason"
FAILED_TEST = re.compile(r"(?:^|\s)(?:FAILED|ERROR) (tests/[^\s:]+\.py::[^\s\[]+(?:\[[^\]]*\])?)")
ANSI_CODE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# Files of every release (name: NeoPedal-<version><suffix>). Apps up to 0.19 update only with the
# installer .exe & its .sha256 file, apps since 0.20 with the setup ZIP (else the .exe), see neopedal/update.py
BUILD_ASSETS = ("-windows-setup.exe", "-windows-setup.exe.sha256", "-setup.zip", "-source.zip")
# Signed manifest of the build files (tools/sign_release.py, release job): apps since 0.28 install an official
# release only with it (neopedal/release_manifest.py)
MANIFEST_ASSETS = ("-manifest.json", "-manifest.json.sig")
RELEASE_ASSETS = BUILD_ASSETS + MANIFEST_ASSETS
POLL = 30  # seconds between GitHub checks


def run(*command: str, check: bool = True) -> str:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        raise SystemExit(f"Failed: {' '.join(command)}\n{result.stderr.strip()}")
    return result.stdout.strip()


def gh_json(*args: str):
    return json.loads(run("gh", *args) or "null")


def stop(message: str) -> int:
    print(f"\nRelease refused: {message}")
    return 1


def checks_runs(sha: str) -> list[dict]:
    """Checks runs of commit (push & workflow_dispatch: master & preflight branches), newest first"""
    runs = gh_json("run", "list", "--repo", REPO, "--workflow", "checks.yml", "--commit", sha, "--limit", "5",
                   "--json", "databaseId,status,conclusion,event,attempt")
    return [item for item in runs or [] if item["event"] in ("push", "workflow_dispatch")]


def checks_state(sha: str) -> tuple[str, list[str]]:
    """State of Checks on commit: success, failure, running or missing; names of failed jobs"""
    runs = checks_runs(sha)
    if not runs:
        return "missing", []
    if any(item["conclusion"] == "success" for item in runs):
        return "success", []
    latest = runs[0]
    if latest["status"] != "completed":
        return "running", []
    jobs = gh_json("run", "view", str(latest["databaseId"]), "--repo", REPO, "--json", "jobs")["jobs"]
    return "failure", [f"{job['name']} ({job['conclusion']})" for job in jobs if job["conclusion"] != "success"]


def failed_tests(log: str) -> set[str]:
    """Node ids of the tests failed in a job log"""
    found = set()
    for line in ANSI_CODE.sub("", log).splitlines():
        match = FAILED_TEST.search(line)
        if match:
            found.add(match.group(1))
    return found


def flaky_tests() -> set[str] | None:
    """Node ids of the tests marked runner_flaky in the working tree (pytest --collect-only), None if not collected"""
    python = next((path for path in (os.path.join(ROOT, ".venv", "Scripts", "python.exe"),
                                     os.path.join(ROOT, ".venv", "bin", "python")) if os.path.isfile(path)),
                  sys.executable)
    try:
        result = subprocess.run([python, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
                                 "-m", FLAKY_MARKER], cwd=ROOT, capture_output=True, text=True, timeout=900,
                                check=False, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode not in (0, 5):  # 5: no test marked
        return None
    return {line.strip() for line in result.stdout.splitlines() if "::" in line and not line.startswith(" ")}


def job_log(job_id: int) -> str:
    """Log of a job (gh run view --log waits for the whole run, the API does not), empty if not read"""
    result = subprocess.run(["gh", "api", "--allow-escape-sequences", f"repos/{REPO}/actions/jobs/{job_id}/logs"],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return result.stdout if result.returncode == 0 else ""


def flaky_failures(run_id: int) -> tuple[list[str], str]:
    """Failed tests of a Checks run when only tests marked runner_flaky failed, else no test and why"""
    jobs = gh_json("run", "view", str(run_id), "--repo", REPO, "--json", "jobs")["jobs"]
    failed_jobs = [job for job in jobs if job["conclusion"] not in ("success", "skipped")]
    if not failed_jobs:
        return [], "no failed job"
    failed: set[str] = set()
    for job in failed_jobs:
        steps = [step["name"] for step in job.get("steps") or [] if step.get("conclusion") == "failure"]
        if job["conclusion"] != "failure" or not steps or not all(name.startswith("Tests") for name in steps):
            return [], f"{job['name']}: {', '.join(steps) or job['conclusion']}, not only tests"
        tests = failed_tests(job_log(int(job["databaseId"])))
        if not tests:
            return [], f"{job['name']}: no failed test found in its log (crash, timeout or coverage)"
        failed |= tests
    flaky = flaky_tests()
    if flaky is None:
        return [], f"tests marked {FLAKY_MARKER} not collected (pytest -m {FLAKY_MARKER} --collect-only failed)"
    others = sorted(failed - flaky)
    if others:
        more = f" and {len(others) - 5} more" if len(others) > 5 else ""
        return [], f"not marked {FLAKY_MARKER}: {', '.join(others[:5])}{more}"
    return sorted(failed), ""


def rerun_flaky(checks_run: dict) -> bool:
    """Run the failed jobs of a Checks run again when only tests marked runner_flaky failed, on its first attempt
    only (one automatic rerun); True if started"""
    if checks_run.get("attempt", 1) > 1:
        print(f"Checks run {checks_run['databaseId']} was run again already: no automatic rerun")
        return False
    tests, why = flaky_failures(int(checks_run["databaseId"]))
    if not tests:
        print(f"No automatic rerun: {why}")
        return False
    print(f"Only tests marked {FLAKY_MARKER} failed ({', '.join(tests)}): failed jobs run again once", flush=True)
    run("gh", "run", "rerun", str(checks_run["databaseId"]), "--failed", "--repo", REPO)
    for _ in range(40):  # until GitHub shows the new attempt
        time.sleep(3)
        data = gh_json("run", "view", str(checks_run["databaseId"]), "--repo", REPO, "--json", "status,attempt")
        if data["attempt"] > checks_run.get("attempt", 1) or data["status"] != "completed":
            break
    return True


def wait_checks(sha: str, rerun_flakes: bool = True) -> tuple[str, list[str]]:
    """Checks state of commit once completed (see checks_state), failed jobs of runner_flaky tests run again once"""
    rerun_done = False
    while True:
        state, failed = checks_state(sha)
        shown = ""
        while state in ("running", "missing"):
            if state != shown:
                shown = state
                print(f"Checks of {sha[:7]}: {'running' if state == 'running' else 'not started yet'}, waiting...",
                      flush=True)
            time.sleep(POLL)
            state, failed = checks_state(sha)
        if state != "failure" or not rerun_flakes or rerun_done:
            return state, failed
        runs = checks_runs(sha)
        if not runs or not rerun_flaky(runs[0]):
            return state, failed
        rerun_done = True


def build_run(sha: str) -> dict | None:
    """Push build run of commit (build-release.yml on a push to master), None if the push started none"""
    runs = gh_json("run", "list", "--repo", REPO, "--workflow", WORKFLOW, "--commit", sha, "--event", "push",
                   "--limit", "1", "--json", "databaseId,status,conclusion")
    return runs[0] if runs else None


def wait_build(sha: str) -> dict | None:
    """Push build run of commit once completed, None if none"""
    item = build_run(sha)
    if item is not None and item["status"] != "completed":
        print(f"Build of {sha[:7]} (push): running, waiting... https://github.com/{REPO}/actions/runs/"
              f"{item['databaseId']}", flush=True)
    while item is not None and item["status"] != "completed":
        time.sleep(POLL)
        item = build_run(sha)
    return item


def build_files(run_id: int) -> bool:
    """Build run kept the files of a release (source & windows artifacts, not expired)"""
    data = gh_json("api", f"repos/{REPO}/actions/runs/{run_id}/artifacts")
    names = {item["name"] for item in (data or {}).get("artifacts", []) if not item.get("expired")}
    return set(BUILD_ARTIFACTS) <= names


def reusable_build(sha: str, version: str, bump: str) -> tuple[int | None, str]:
    """Push build run whose files the release can publish (same commit & version, passed), else None and why"""
    item = wait_build(sha)
    if item is None:
        return None, "no build started by the push of this commit"
    if item["conclusion"] != "success":
        return None, f"build of the push {item['conclusion']}: https://github.com/{REPO}/actions/runs/{item['databaseId']}"
    if not build_files(int(item["databaseId"])):
        return None, "the push built nothing (changelog sections pushed later?)"
    if bump != "auto" and run(sys.executable, "tools/next_version.py", "--bump", "auto") != version:
        return None, f"the push built the version from commit titles, not --bump {bump}"
    return int(item["databaseId"]), ""


def start_release(bump: str, build_run_id: int | None = None) -> int:
    """Start release workflow on master (publishing the files of build_run_id if given), id of its run"""
    before = {item["databaseId"] for item in gh_json(
        "run", "list", "--repo", REPO, "--workflow", WORKFLOW, "--limit", "10", "--json", "databaseId") or []}
    inputs = ["-f", f"bump={bump}"] + (["-f", f"build_run_id={build_run_id}"] if build_run_id else [])
    run("gh", "workflow", "run", WORKFLOW, "--repo", REPO, "--ref", "master", *inputs)
    for _ in range(20):
        time.sleep(3)
        for item in gh_json("run", "list", "--repo", REPO, "--workflow", WORKFLOW, "--limit", "10",
                            "--json", "databaseId,event") or []:
            if item["databaseId"] not in before and item["event"] == "workflow_dispatch":
                return int(item["databaseId"])
    raise SystemExit("Release workflow started, but its run was not found: see the Actions tab on GitHub")


def follow(run_id: int) -> str:
    """Wait for workflow run, printing job changes, its conclusion"""
    shown: set[str] = set()
    while True:
        data = gh_json("run", "view", str(run_id), "--repo", REPO, "--json", "status,conclusion,jobs")
        for job in data["jobs"]:
            line = f"  {job['name']}: {job['conclusion'] or job['status']}"
            if line not in shown:
                shown.add(line)
                print(line, flush=True)
        if data["status"] == "completed":
            return data["conclusion"]
        time.sleep(POLL)


def ask(question: str) -> bool:
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes", "o", "oui")
    except EOFError:
        return False


def changelogs_without(version: str, commit: str = "HEAD") -> list[str]:
    """Changelogs of commit without the section of version"""
    pattern = re.compile(rf"^## {re.escape(version)}\b", re.MULTILINE)
    return [name for name in ("CHANGELOG.md", "CHANGELOG.fr.md")
            if not pattern.search(run("git", "show", f"{commit}:{name}", check=False))]


def write_release_commit(snapshot_sha: str, message: list[str]) -> str:
    """Commit of the snapshot tree (the files Checks passed) on master, index reset to it (the working tree is
    kept: changes made since the snapshot stay uncommitted). Its sha, empty if refused"""
    head = run("git", "rev-parse", "HEAD")
    if run("git", "rev-parse", f"{snapshot_sha}^") != head:
        print("Release commit not written: HEAD changed since the preflight snapshot, commit by hand")
        return ""
    tree = run("git", "rev-parse", f"{snapshot_sha}^{{tree}}")
    args = [item for part in message for item in ("-m", part)]
    sha = run("git", "commit-tree", tree, "-p", head, *args)
    run("git", "update-ref", "-m", "release.py --preflight: release commit", "refs/heads/master", sha, head)
    # Index of the committed files = the new commit, working tree untouched; other files keep what was staged
    # (another session's hunks staged meanwhile)
    changed = [path for path in run("git", "diff", "--name-only", "--no-renames", head, sha).splitlines() if path]
    for start in range(0, len(changed), 200):  # command line length
        run("git", "reset", "--quiet", sha, "--", *changed[start:start + 200])
    return sha


def preflight(options: argparse.Namespace) -> int:
    """--preflight: Checks on the working tree (tools/ci_preflight.py), then offer to write the release commit"""
    import ci_preflight

    status, snapshot_sha = ci_preflight.run_preflight(options.yes)
    if status != 0:
        return stop("Checks did not pass on the working tree: fix, then run python tools/release.py --preflight again")
    if run("git", "branch", "--show-current") != "master":
        print("\nNot on master: switch to master and commit there to release")
        return 0
    changed = run("git", "diff", "--name-only", "HEAD", snapshot_sha).splitlines()
    if not changed:
        print("\nNothing to commit: the tested files are the ones of HEAD")
        return 0
    print(f"\nRelease commit: the {len(changed)} files Checks tested (preflight {snapshot_sha[:7]}), on master "
          f"{run('git', 'rev-parse', '--short', 'HEAD')}")
    message = [part for part in options.message or [] if part.strip()]
    if not message:
        try:
            title = input("Title of the release commit (empty: no commit): ").strip()
        except EOFError:
            title = ""
        message = [title] if title else []
    if not message or (not options.yes and not ask(f"Write the commit \"{message[0]}\"?")):
        print("No commit written. Commit by hand, push, then python tools/release.py")
        return 0
    sha = write_release_commit(snapshot_sha, message)
    if not sha:
        return 1
    print(f"Committed {sha[:7]} {message[0]}")
    if run("git", "status", "--porcelain", "--untracked-files=no"):
        print("Files changed since the preflight stay uncommitted (not tested by Checks)")
    version = run(sys.executable, "tools/next_version.py", "--bump", options.bump)
    missing = changelogs_without(version) if version else []
    if missing:
        print(f"Warning: {', '.join(missing)} without '## {version}': write it, git commit --amend "
              "(documentation only, the preflight stays valid)")
    print(f"Next: git push (pre-push hook, then Checks & the build of {version or 'the release'} start on GitHub), "
          "then python tools/release.py")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="Usage" + __doc__.split("Usage", 1)[1])
    parser.add_argument("--bump", choices=("auto", "patch", "minor", "major"), default="auto")
    parser.add_argument("--dry-run", action="store_true", help="check only, publish nothing")
    parser.add_argument("--yes", action="store_true", help="do not ask before publishing")
    parser.add_argument("--preflight", action="store_true",
                        help="Checks on the working tree first, then offer to write the release commit")
    parser.add_argument("-m", "--message", action="append",
                        help="--preflight: message of the release commit (title, then paragraphs)")
    options = parser.parse_args()

    run("gh", "auth", "status")
    if options.preflight:
        return preflight(options)
    run("git", "fetch", "--quiet", "--tags", "origin")
    if run("git", "branch", "--show-current") != "master":
        return stop("switch to master first")
    if run("git", "status", "--porcelain", "--untracked-files=no"):
        return stop("master has uncommitted changes: commit and push them, or stash them")
    sha = run("git", "rev-parse", "HEAD")
    if sha != run("git", "rev-parse", "origin/master"):
        return stop("local master differs from GitHub: push your commits (or pull) first")

    version = run(sys.executable, "tools/next_version.py", "--bump", options.bump)
    if not version:
        return stop("nothing to release since the last version (or only documentation changed)")
    print(f"Next version: {version} (master {sha[:7]})")
    for changelog in ("CHANGELOG.md", "CHANGELOG.fr.md"):
        if subprocess.run([sys.executable, "tools/gen_release_notes.py", "--check-changelog", version,
                           "--changelog", changelog], cwd=ROOT, capture_output=True, check=False).returncode:
            return stop(f"{changelog} has no '## {version}' section: write it (both languages), commit, push")
    print("Changelogs: both have the section")

    state, failed = wait_checks(sha)
    if state != "success":
        return stop(f"Checks failed on {sha[:7]}: {', '.join(failed)}. Cancelled jobs (GitHub outage): "
                    "rerun them with \"gh run rerun <id> --failed\", then run this again")
    print("Checks: passed")
    build_run_id, why = reusable_build(sha, version, options.bump)
    if build_run_id:
        print(f"Build: files of the push build https://github.com/{REPO}/actions/runs/{build_run_id} published")
    else:
        print(f"Build: by the release run ({why})")
    if options.dry_run:
        print(f"\nReady to publish {version} (dry run: nothing published)")
        return 0
    if not options.yes and not ask(f"\nPublish {version}?"):
        return stop("cancelled")

    run_id = start_release(options.bump, build_run_id)
    print(f"Release workflow: https://github.com/{REPO}/actions/runs/{run_id}")
    conclusion = follow(run_id)
    if conclusion != "success":
        return stop(f"release workflow {conclusion}: see https://github.com/{REPO}/actions/runs/{run_id}")

    release = gh_json("release", "view", f"v{version}", "--repo", REPO, "--json", "url,assets")
    names = {asset["name"] for asset in release["assets"]}
    missing = [f"NeoPedal-{version}{suffix}" for suffix in RELEASE_ASSETS
               if f"NeoPedal-{version}{suffix}" not in names]
    if missing:
        print(f"\nPublished, but files are missing: {', '.join(missing)}")
        return 1
    print(f"\nPublished {version}: {release['url']}")
    for name in sorted(names):
        print(f"  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
