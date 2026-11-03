"""
Run the checks of GitHub before pushing: lint, type check (Windows & Linux), tests with coverage

Same commands as the Checks workflow, so a push to master is not the first time they run.
Also warns when the changelogs have no section for the next version (needed to publish it), when an
overlay looks different with no before / after image in docs/changes (tools/make_change_visual.py --scan),
and lints edited workflows when actionlint / zizmor are installed.

Installed tools must be the versions of requirements-dev-lock.txt (what Checks install): else a warning, and
the pre-push hook refuses the push. The hook also refuses a release commit (new version section in
CHANGELOG.md) whose code never passed Checks: run tools/ci_preflight.py first.

Tests are spread over every CPU when pytest-xdist is installed (requirements-dev.txt), as on CI. The pre-push hook
runs them without coverage (Checks measure it) and stops after 20 failures (--maxfail=20).

Usage (from project root):
    python tools/check.py                 every check (tests with coverage)
    python tools/check.py --quick         without tests
    python tools/check.py --matrix        tests on Windows 3.14, Windows 3.11 & Linux 3.14 (WSL) at once
    python tools/check.py --install-hook  run every check before each push to master (git pre-push hook)
"""

from __future__ import annotations

import argparse
import io
import itertools
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MATRIX_HELP = """\
--matrix: the test suite (no coverage) on three environments at once, the ones Checks found broken on 0.28.0
(Windows-only tests, the Python 3.11 crash, Linux-only failures). Not in the pre-push hook: run it before the
release commit and after each change of I/O, threads or platform code. Missing environments are skipped:

  Windows, Python 3.14   repo .venv (the one of tools/check.py), tests run in the working tree
  Windows, Python 3.11   repo .venv311 (git-ignored), tests run on a copy of the working tree. Set up once:
                           uv venv --python 3.11 .venv311
                           uv pip install --python .venv311 -r requirements-dev-lock.txt
  Linux, Python 3.14     WSL distribution (NEOPEDAL_WSL_DISTRO, else the default one) with a venv at
                         ~/.venvs/neopedal-py314 (NEOPEDAL_WSL_VENV), tests run on a copy in ~/.cache/neopedal-matrix.
                         Set up once (Ubuntu 24.04):
                           wsl --install -d Ubuntu-24.04
                           sudo apt-get install -y libegl1 libxkbcommon0 libgl1 libpulse0 libfontconfig1 libdbus-1-3
                           curl -LsSf https://astral.sh/uv/install.sh | sh
                           uv venv --python 3.14 ~/.venvs/neopedal-py314
                           uv pip install --python ~/.venvs/neopedal-py314 -r requirements-dev-lock.txt
                         (the last command from the repo folder, /mnt/<drive>/...)

Each run gets its share of the CPUs (pytest-xdist) and its own range of test server ports (NEOPEDAL_TEST_PORT_OFFSET):
Windows runs share the localhost ports, so they run one after another while the tests do not read that offset.
Full output of each run: <temp>/neopedal-matrix/<name>.log
"""
PORT_OFFSET_ENV = "NEOPEDAL_TEST_PORT_OFFSET"  # added to the fixed localhost ports of server tests
PORT_TESTS = ("tests/test_command_server.py", "tests/test_web_dashboard.py")
WSL_VENV = "$HOME/.venvs/neopedal-py314"
WSL_TREE = "$HOME/.cache/neopedal-matrix"
MATRIX_DIR = os.path.join(tempfile.gettempdir(), "neopedal-matrix")
GIT_IDENTITY = ["-c", "user.name=matrix", "-c", "user.email=matrix@localhost", "-c", "commit.gpgsign=false"]
SUMMARY_LINE = re.compile(r"^=+ .+ in [\d.]+s.* =+$|^\d+ (passed|failed).* in [\d.]+s")

HOOK = """#!/bin/sh
# Installed by "python tools/check.py --install-hook": every check before a push to master
# (pushes to other branches are not checked)
while read -r local_ref local_sha remote_ref remote_sha; do
  if [ "$remote_ref" = "refs/heads/master" ]; then
    to_master=1
  fi
done
[ -z "$to_master" ] && exit 0
python=python3
[ -x .venv/Scripts/python.exe ] && python=.venv/Scripts/python.exe
[ -x .venv/bin/python ] && python=.venv/bin/python
exec "$python" tools/check.py --pre-push
"""


def run(title: str, command: list[str], env: dict | None = None) -> bool:
    """Run one check, True if passed"""
    print(f"\n=== {title}", flush=True)
    started = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, env={**os.environ, **(env or {})}, check=False)
    passed = result.returncode == 0
    print(f"--- {title}: {'passed' if passed else 'FAILED'} ({time.monotonic() - started:.0f} s)", flush=True)
    return passed


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()


def uncommitted_changes() -> list[str]:
    """Tracked files changed but not committed (untracked files ignored)"""
    return [line for line in git("status", "--porcelain", "--untracked-files=no").splitlines() if line.strip()]


def changelog_warnings() -> list[str]:
    """Changelogs without section of next version (a release needs both)"""
    version = subprocess.run([sys.executable, "tools/next_version.py", "--bump", "auto"], cwd=ROOT,
                             capture_output=True, text=True, check=False).stdout.strip()
    if not version:
        return []
    missing = []
    for changelog in ("CHANGELOG.md", "CHANGELOG.fr.md"):
        result = subprocess.run([sys.executable, "tools/gen_release_notes.py", "--check-changelog", version,
                                 "--changelog", changelog], cwd=ROOT, capture_output=True, check=False)
        if result.returncode != 0:
            missing.append(f"{changelog} has no '## {version}' section (needed to publish {version})")
    return missing


def visual_warnings() -> list[str]:
    """Overlays whose render changed since origin/master with no before / after image in docs/changes
    (tools/make_change_visual.py --scan): the release notes would not show the change"""
    base = "origin/master" if git("rev-parse", "--verify", "--quiet", "origin/master") else "HEAD"
    result = subprocess.run([sys.executable, "tools/make_change_visual.py", "--scan", "--base", base], cwd=ROOT,
                            capture_output=True, text=True, check=False, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    if result.returncode == 0:
        return []
    if result.returncode != 1:
        return [f"overlay visual scan failed: {(result.stderr.strip().splitlines() or ['?'])[-1]}"]
    missing = [line.split()[0] for line in result.stdout.splitlines() if line.endswith("<- no image yet")]
    return [f"overlay render changed with no before / after image: {', '.join(missing)} "
            "(python tools/make_change_visual.py --scan, or [visual] in the commit message)"]


def workflow_linters() -> list[tuple[str, list[str]]]:
    """actionlint & zizmor on workflows changed since origin/master, if installed"""
    changed = [path for path in git("diff", "--name-only", "origin/master", "--", ".github/workflows").splitlines()
               if path.endswith((".yml", ".yaml")) and os.path.exists(os.path.join(ROOT, path))]
    if not changed:
        return []
    linters = []
    for name, args in (("actionlint", []), ("zizmor", ["--offline"])):
        executable = shutil.which(name)
        if executable:
            linters.append((f"{name} (workflows)", [executable, *args, *changed]))
        else:
            print(f"(workflows changed: {name} not installed, skipped)")
    return linters


def lock_mismatches(lock: str = "requirements-dev-lock.txt") -> list[str]:
    """Installed packages not at the version of the lock Checks install (only those for this OS & Python)"""
    from importlib import metadata

    try:
        from packaging.requirements import Requirement
    except ImportError:
        return ["packaging not installed"]
    mismatches = []
    with open(os.path.join(ROOT, lock), encoding="utf-8") as file:
        for line in file:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            requirement = Requirement(line)
            if requirement.marker and not requirement.marker.evaluate():
                continue
            wanted = next(iter(requirement.specifier)).version
            try:
                installed = metadata.version(requirement.name)
            except metadata.PackageNotFoundError:
                installed = "not installed"
            if installed != wanted:
                mismatches.append(f"{requirement.name} {installed} (Checks: {wanted})")
    return mismatches


def new_release_versions(base: str, head: str) -> list[str]:
    """Versions whose section the commits base..head add to CHANGELOG.md (a release commit)"""
    diff = git("diff", "--unified=0", base, head, "--", "CHANGELOG.md")
    return [line[4:].split()[0] for line in diff.splitlines()
            if line.startswith("+## ") and line[4:5].isdigit()]


def release_without_checks() -> str:
    """Refusal message when a push to master adds a release section to the changelog while its code never
    passed Checks (master or tools/ci_preflight.py), empty if fine. NEOPEDAL_SKIP_PREFLIGHT=1: not checked"""
    if os.environ.get("NEOPEDAL_SKIP_PREFLIGHT") == "1":
        return ""
    head = git("rev-parse", "HEAD")
    base = git("rev-parse", "--verify", "--quiet", "origin/master")
    versions = new_release_versions(base, head) if base else []
    if not versions:
        return ""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from ci_preflight import passed_base

        if passed_base(head):
            return ""
    except (OSError, ValueError, subprocess.CalledProcessError, SystemExit) as error:
        return f"release {', '.join(versions)}: Checks state not read ({error})"
    return (f"release {', '.join(versions)}: Checks never passed on this code. Run python tools/ci_preflight.py "
            "first (whole matrix on a branch, master untouched), then push again")


def parallel_test_args() -> list[str]:
    """pytest-xdist arguments: tests spread over every CPU, none if not installed (one process)"""
    import importlib.util

    if importlib.util.find_spec("xdist") is None:
        print("(pytest-xdist not installed: tests run in one process, pip install -r requirements-dev.txt)")
        return []
    return ["-n", "auto"]


def test_command(python: list[str], workers: int | str = 0, coverage: bool = True, maxfail: int = 0) -> list[str]:
    """pytest command of the checks (workers: pytest-xdist -n value, 0 for one process)"""
    command = [*python, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    if workers:
        command += ["-n", str(workers)]
    command.append("--timeout=300")
    if maxfail:
        command.append(f"--maxfail={maxfail}")
    if coverage:
        command += ["--cov=neopedal", "--cov-report=term:skip-covered"]
    return command


class MatrixRun:
    """One environment of --matrix: Python command, run in a thread with output to a log file"""

    def __init__(self, name: str, python: list[str], cwd: str, env: dict | None = None, prepare=None,
                 wsl_script: str = ""):
        self.name = name
        self.python = python  # Python of the environment (or the wsl.exe command running wsl_script)
        self.cwd = cwd
        self.env = env or {}
        self.prepare = prepare  # called first in the thread (copy of the working tree)
        self.wsl_script = wsl_script  # shell script prefix run in WSL, followed by the pytest arguments
        self.command: list[str] = []
        self.after: MatrixRun | None = None  # run that must end first (same localhost ports)
        self.done = threading.Event()
        self.returncode: int | None = None
        self.seconds = 0.0
        self.log = os.path.join(MATRIX_DIR, re.sub(r"[^\w.-]+", "-", name.lower()).strip("-") + ".log")

    def set_test_args(self, args: list[str]) -> None:
        if self.wsl_script:
            self.command = [*self.python, " ".join([self.wsl_script, *args])]
        else:
            self.command = [*self.python, *args]

    def run(self) -> None:
        try:
            if self.after is not None:
                self.after.done.wait()
            started = time.monotonic()
            with open(self.log, "w", encoding="utf-8", errors="replace") as log:
                try:
                    if self.prepare is not None:
                        self.prepare()
                    result = subprocess.run(self.command, cwd=self.cwd, env={**os.environ, **self.env},
                                            stdout=log, stderr=subprocess.STDOUT, check=False)
                    self.returncode = result.returncode
                except (OSError, subprocess.SubprocessError) as error:
                    log.write(f"\n{self.name}: not started ({error})\n")
                    self.returncode = -1
            self.seconds = time.monotonic() - started
        finally:
            self.done.set()

    def report(self) -> str:
        """Result line, test summary & failed tests of the log"""
        try:
            with open(self.log, encoding="utf-8", errors="replace") as file:
                lines = file.read().splitlines()
        except OSError:
            lines = []
        summary = next((line.strip() for line in reversed(lines) if SUMMARY_LINE.search(line.strip())),
                       next((line.strip() for line in reversed(lines) if line.strip()), "no output"))
        failed = [line.strip() for line in lines if line.startswith(("FAILED ", "ERROR "))]
        state = "passed" if self.returncode == 0 else "FAILED"
        text = [f"--- {self.name}: {state} ({self.seconds:.0f} s): {summary}"]
        text += [f"    {line}" for line in failed[:30]]
        if len(failed) > 30:
            text.append(f"    ... {len(failed) - 30} more")
        text.append(f"    log: {self.log}")
        return "\n".join(text)


def venv_python(folder: str) -> str | None:
    """Python of a venv of the repo (Windows or Linux layout), None if missing"""
    for parts in (("Scripts", "python.exe"), ("bin", "python")):
        path = os.path.join(ROOT, folder, *parts)
        if os.path.isfile(path):
            return path
    return None


def tree_files() -> list[tuple[str, bool]]:
    """Files of the working tree as Checks get them (tracked & new files, ignored & deleted files left out),
    with their executable bit in git"""
    executable = set()
    for line in git("ls-files", "-s").splitlines():
        mode, _, rest = line.partition(" ")
        if mode == "100755" and "\t" in rest:
            executable.add(rest.split("\t", 1)[1])
    listed = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", check=False).stdout
    return [(path, path in executable) for path in dict.fromkeys(listed.split("\0"))
            if path and os.path.isfile(os.path.join(ROOT, path))]


def remove_tree(target: str) -> None:
    """Folder removed with its read-only files (git objects of the copy of an earlier run: ignore_errors left them,
    and the copy failed with "file already exists")"""

    def writable(function, path, _error) -> None:
        os.chmod(path, stat.S_IWRITE)
        function(path)

    if not os.path.exists(target):
        return
    if sys.version_info >= (3, 12):
        shutil.rmtree(target, onexc=writable)
    else:
        shutil.rmtree(target, onerror=writable)  # Python 3.11: no onexc


def copy_tree(target: str) -> None:
    """Copy of the working tree (tree_files) in target, emptied first, committed in a git repo of its own like the
    checkout of Checks (tests read git: source version, executable bits of the launchers)"""
    remove_tree(target)
    os.makedirs(target)
    files = tree_files()
    for path, flag in files:
        destination = os.path.join(target, path)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, path), destination)
        # Mode on disk as in the index: git compares them where core.filemode is on (Linux: "M run.sh" otherwise)
        os.chmod(destination, 0o700 if flag else 0o600)

    def copy_git(*args: str) -> None:
        subprocess.run(["git", *GIT_IDENTITY, *args], cwd=target, capture_output=True, check=False)

    copy_git("init", "-q")
    copy_git("add", "--all")
    executable = [path for path, flag in files if flag]
    if executable:
        copy_git("update-index", "--chmod=+x", "--", *executable)  # core.filemode is off on Windows
    copy_git("commit", "-q", "--no-verify", "-m", "tools/check.py --matrix snapshot")


def tree_tar() -> bytes:
    """Working tree (tree_files) as a tar archive, executable bits kept"""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for path, executable in tree_files():
            info = tar.gettarinfo(os.path.join(ROOT, path), arcname=path)
            info.mode = 0o755 if executable else 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with open(os.path.join(ROOT, path), "rb") as file:
                tar.addfile(info, file)
    return buffer.getvalue()


def ports_isolated() -> bool:
    """Server tests add NEOPEDAL_TEST_PORT_OFFSET to their localhost ports (two Windows runs can share the host)"""
    for path in PORT_TESTS:
        try:
            with open(os.path.join(ROOT, path), encoding="utf-8") as file:
                if PORT_OFFSET_ENV not in file.read():
                    return False
        except OSError:
            pass
    return True


def wsl_command() -> tuple[list[str] | None, str]:
    """wsl.exe command running a shell script in the Linux distribution with Python 3.14 & Qt, or None and why"""
    if sys.platform != "win32":
        return None, "not Windows"
    executable = shutil.which("wsl.exe")
    if executable is None:
        return None, "wsl.exe not found"
    try:
        listed = subprocess.run([executable, "--list", "--quiet"], capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        return None, f"wsl.exe failed ({error})"
    names = [name.strip() for name in listed.stdout.decode("utf-16-le", errors="replace").replace("\0", "")
             .splitlines() if name.strip()]
    if listed.returncode != 0 or not names:
        return None, "WSL not installed or no Linux distribution"
    distro = os.environ.get("NEOPEDAL_WSL_DISTRO", "")
    if distro and distro not in names:
        return None, f"no WSL distribution {distro} (installed: {', '.join(names)})"
    command = [executable, *(["--distribution", distro] if distro else []), "--exec", "sh", "-c"]
    venv = os.environ.get("NEOPEDAL_WSL_VENV", WSL_VENV)
    probe = (f"{venv}/bin/python -c 'import sys; from PySide6.QtGui import QGuiApplication; "
             "print(sys.version_info[0], sys.version_info[1])'")
    try:
        result = subprocess.run([*command, probe], capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        return None, f"WSL probe failed ({error})"
    if result.returncode != 0:
        last = (result.stderr.strip().splitlines() or ["?"])[-1]
        return None, f"no venv with PySide6 & Qt libraries at {venv} in WSL {distro or '(default)'}: {last}"
    if result.stdout.split() != ["3", "14"]:
        return None, f"{venv} in WSL is Python {'.'.join(result.stdout.split())}, not 3.14"
    return command, ""


def matrix_runs() -> tuple[list[MatrixRun], list[str]]:
    """Runs of --matrix found on this PC, and the environments skipped with why"""
    runs: list[MatrixRun] = []
    skipped: list[str] = []
    qt_env = {"QT_QPA_PLATFORM": "offscreen"}
    python = venv_python(".venv") or sys.executable
    system = "Windows" if sys.platform == "win32" else sys.platform
    version = subprocess.run([python, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                             capture_output=True, text=True, check=False).stdout.strip()
    runs.append(MatrixRun(f"{system} Python {version} (.venv)", [python], ROOT, {**qt_env, PORT_OFFSET_ENV: "0"}))

    python311 = venv_python(".venv311")
    if python311 is None:
        skipped.append("Windows Python 3.11: no .venv311 (uv venv --python 3.11 .venv311 && "
                       "uv pip install --python .venv311 -r requirements-dev-lock.txt)")
    else:
        copy = os.path.join(MATRIX_DIR, "py311-tree")
        runs.append(MatrixRun(f"{system} Python 3.11 (.venv311)", [python311], copy,
                              {**qt_env, PORT_OFFSET_ENV: "1000"}, prepare=lambda: copy_tree(copy)))

    wsl, why = wsl_command()
    if wsl is None:
        skipped.append(f"Linux Python 3.14 (WSL): {why} (set up: python tools/check.py --help)")
    else:
        venv = os.environ.get("NEOPEDAL_WSL_VENV", WSL_VENV)
        extract = (f"rm -rf {WSL_TREE} && mkdir -p {WSL_TREE} && tar -xf - -C {WSL_TREE} && "
                   f"(cd {WSL_TREE} && git init -q && git add --all && git {' '.join(GIT_IDENTITY)} commit -q "
                   "--no-verify -m snapshot || true)")
        script = (f"cd {WSL_TREE} && ({venv}/bin/python tools/check.py --check-lock || true) && "
                  f"QT_QPA_PLATFORM=offscreen {PORT_OFFSET_ENV}=2000 {venv}/bin/python")
        runs.append(MatrixRun("Linux Python 3.14 (WSL)", wsl, ROOT, wsl_script=script, prepare=lambda: subprocess.run(
            [*wsl, extract], input=tree_tar(), capture_output=True, check=True)))
    return runs, skipped


def lock_warnings(runs: list[MatrixRun]) -> None:
    """Warn about environments of this OS whose packages differ from requirements-dev-lock.txt (WSL: in its log)"""
    for item in runs:
        if item.wsl_script:
            continue
        result = subprocess.run([item.python[0], os.path.join(ROOT, "tools", "check.py"), "--check-lock"],
                                cwd=ROOT, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            print(f"Warning: {item.name} differs from requirements-dev-lock.txt:\n{result.stdout.rstrip()}")


def run_matrix() -> int:
    """--matrix: test suite on every environment found, at once (MATRIX_HELP)"""
    os.makedirs(MATRIX_DIR, exist_ok=True)
    runs, skipped = matrix_runs()
    for reason in skipped:
        print(f"Skipped: {reason}")
    local = [item for item in runs if not item.wsl_script]
    sequential = len(local) > 1 and not ports_isolated()
    if sequential:
        print(f"(Windows runs one after another: {', '.join(PORT_TESTS)} do not read {PORT_OFFSET_ENV} yet)")
        for previous, item in itertools.pairwise(local):
            item.after = previous
    at_once = len(runs) - (len(local) - 1 if sequential else 0)
    workers = max(2, (os.cpu_count() or 2) // at_once)
    lock_warnings(runs)
    for item in runs:
        # No coverage (the 3.11 crash came from its C tracer), every failure listed
        item.set_test_args(test_command([], workers, coverage=False))
        print(f"Started: {item.name}, {workers} workers" + (f", after {item.after.name}" if item.after else ""),
              flush=True)
    threads = [threading.Thread(target=item.run, name=item.name, daemon=True) for item in runs]
    for thread in threads:
        thread.start()
    pending = list(runs)
    while pending:
        for item in list(pending):
            if item.done.wait(timeout=1):
                pending.remove(item)
                print(item.report(), flush=True)
    failed = [item.name for item in runs if item.returncode != 0]
    print()
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        return 1
    print(f"Tests passed on {len(runs)} environment(s)" + (f", {len(skipped)} skipped" if skipped else ""))
    return 0


def install_hook() -> int:
    hooks = git("rev-parse", "--git-path", "hooks")
    path = os.path.join(ROOT, hooks, "pre-push")
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as file:
            if "tools/check.py" not in file.read():
                print(f"{path} already exists (not from tools/check.py): not replaced")
                return 1
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write(HOOK)
    os.chmod(path, 0o755)
    print(f"Installed {path}: every check runs before each push to master")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0], epilog=MATRIX_HELP,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quick", action="store_true", help="skip tests")
    parser.add_argument("--matrix", action="store_true",
                        help="tests only, on Windows 3.14, Windows 3.11 & Linux 3.14 (WSL) at once (see below)")
    parser.add_argument("--install-hook", action="store_true", help="install git pre-push hook")
    parser.add_argument("--check-lock", action="store_true",
                        help="only compare installed packages with requirements-dev-lock.txt")
    parser.add_argument("--pre-push", action="store_true", help=argparse.SUPPRESS)
    options = parser.parse_args()
    if options.install_hook:
        return install_hook()
    if options.matrix:
        return run_matrix()
    if options.check_lock:
        mismatches = lock_mismatches()
        print("\n".join(f"  {item}" for item in mismatches) or "Installed versions are the ones of Checks")
        return 1 if mismatches else 0

    if options.pre_push and uncommitted_changes():
        print("Push to master refused: commit or stash your changes first, the checks would not test what you push:")
        print("\n".join(uncommitted_changes()))
        return 1
    if options.pre_push and (refusal := release_without_checks()):
        print(f"Push to master refused: {refusal}")
        return 1

    mismatches = lock_mismatches()
    if mismatches:
        print("Installed versions differ from the ones of Checks (requirements-dev-lock.txt):")
        print("\n".join(f"  {item}" for item in mismatches))
        print(f"Fix: {sys.executable} -m pip install -r requirements-dev-lock.txt")
        if options.pre_push:
            print("Push to master refused: the checks would not test what Checks run")
            return 1

    python = sys.executable
    checks: list[tuple[str, list[str], dict | None]] = [
        ("ruff", [python, "-m", "ruff", "check", "."], None),
        ("mypy (Windows)", [python, "-m", "mypy", "--platform", "win32", "neopedal"], None),
        ("mypy (Linux)", [python, "-m", "mypy", "--platform", "linux", "neopedal"], None),
    ]
    checks += [(title, command, None) for title, command in workflow_linters()]
    if not options.quick:
        workers = "auto" if parallel_test_args() else 0
        # Hook: no coverage (Checks measure it), stops after 20 failures (0.28.0: a leak of patches failed
        # hundreds of tests, the hook ran 13-16 minutes for each fix)
        title = "tests" if options.pre_push else "tests with coverage"
        checks.append((title, test_command([python], workers, coverage=not options.pre_push,
                                           maxfail=20 if options.pre_push else 0), {"QT_QPA_PLATFORM": "offscreen"}))

    failed = [title for title, command, env in checks if not run(title, command, env)]
    warnings = changelog_warnings() + visual_warnings()
    print()
    for warning in warnings:
        print(f"Warning: {warning}")
    if failed:
        print(f"FAILED: {', '.join(failed)}" + (" (push refused)" if options.pre_push else ""))
        return 1
    print("Every check passed" + (" (tests skipped)" if options.quick else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
