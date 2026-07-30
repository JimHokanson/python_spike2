#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build and verify the spike2io release artifacts.

Produces the three files that get uploaded to PyPI:

    dist/spike2io-X.Y.Z-py3-none-win_amd64.whl    Requires-Python >=3.9
    dist/spike2io-X.Y.Z-py3-none-any.whl          Requires-Python >=3.14
    dist/spike2io-X.Y.Z.tar.gz

and then checks them. The checks matter: the two wheels are built from the
same source tree with different configurations, and a stale build/lib once
produced an 'any' wheel carrying the Windows binaries. That is invisible
unless something looks inside the archive, so this script does.

Everything it creates apart from dist/ is removed again, including the
throwaway virtualenv it uses for the build tooling, even if a step fails.

Usage
-----
    py -3.14 release.py             # build + verify (recommended)
    py -3.14 release.py --no-venv   # reuse the current interpreter's
                                    # build/twine instead of making a venv
    py -3.14 release.py --keep-venv # leave the venv for debugging

This script deliberately does NOT upload. Publishing is irreversible: a
version number, once used, can never be reused on PyPI even if the release
is deleted. The upload commands are printed at the end so that step stays a
conscious act.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).parent.resolve()
DIST = HERE / "dist"
PROJECT = "spike2io"

# Intermediates this script is allowed to delete from the source tree.
INTERMEDIATES = ("build", f"{PROJECT}.egg-info", ".eggs")


# ----------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------

class Fail(Exception):
    """A check failed; the release must not be uploaded."""


def step(msg: str) -> None:
    print(f"\n\033[1m==> {msg}\033[0m" if sys.stdout.isatty() else f"\n==> {msg}")


def ok(msg: str) -> None:
    print(f"    [ok]   {msg}")


def warn(msg: str) -> None:
    print(f"    [warn] {msg}")


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    """Run a command, surfacing its output only when it fails."""
    proc = subprocess.run(cmd, cwd=str(HERE), capture_output=True,
                          text=True, **kw)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise Fail(f"command failed: {' '.join(cmd)}")
    return proc


def read_version() -> str:
    text = (HERE / "ced" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.M)
    if match is None:
        raise Fail("could not find __version__ in ced/__init__.py")
    return match.group(1)


def clean_intermediates() -> None:
    for name in INTERMEDIATES:
        shutil.rmtree(HERE / name, ignore_errors=True)


# ----------------------------------------------------------------------
# Pre-flight
# ----------------------------------------------------------------------

def preflight(version: str) -> None:
    step(f"Pre-flight for {PROJECT} {version}")

    # The sdist is built from the working tree, not from HEAD, so anything
    # uncommitted silently becomes part of the release.
    try:
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=str(HERE),
                               capture_output=True, text=True).stdout.strip()
    except FileNotFoundError:
        dirty = ""
        warn("git not found; skipping clean-tree check")
    if dirty:
        warn("working tree has uncommitted changes -- these WILL be included:")
        for line in dirty.splitlines():
            print(f"           {line}")
    else:
        ok("git working tree is clean")

    # Catching an already-published version here is far better than finding
    # out from a rejected upload, because the build is wasted either way.
    try:
        from urllib.error import HTTPError
        from urllib.request import urlopen
        try:
            with urlopen(f"https://pypi.org/pypi/{PROJECT}/json", timeout=10) as fh:
                released = set(json.load(fh).get("releases", {}))
        except HTTPError as exc:
            if exc.code != 404:
                raise
            # 404 means the project has never been published, which is
            # exactly what we want for a first release.
            ok(f"'{PROJECT}' is not yet registered on PyPI -- this would be "
               f"the first release")
            return
        if version in released:
            raise Fail(
                f"version {version} is already on PyPI. Version numbers are "
                f"never reusable -- bump __version__ in ced/__init__.py.")
        ok(f"version {version} is not yet on PyPI "
           f"(existing: {', '.join(sorted(released)) or 'none'})")
    except Fail:
        raise
    except Exception as exc:                       # offline, timeout, DNS
        warn(f"could not reach PyPI to check existing versions ({exc})")


# ----------------------------------------------------------------------
# Build
# ----------------------------------------------------------------------

def make_venv(tmp: Path) -> Path:
    step("Creating throwaway build environment")
    venv = tmp / "venv"
    run([sys.executable, "-m", "venv", str(venv)])
    py = venv / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    run([str(py), "-m", "pip", "install", "--quiet", "--upgrade",
         "pip", "build", "twine"])
    ok(f"build tooling installed in {venv}")
    return py


def build_all(py: Path, version: str) -> None:
    step("Building artifacts")
    shutil.rmtree(DIST, ignore_errors=True)
    clean_intermediates()

    for target, what in (("windows", "--wheel"),
                         ("any", "--wheel"),
                         ("windows", "--sdist")):
        # setup.py purges build/lib when the target changes, but clearing it
        # here too keeps this script correct even against an older setup.py.
        clean_intermediates()
        import os
        env = dict(os.environ, SPIKE2IO_WHEEL=target)
        run([str(py), "-m", "build", what], env=env)
        ok(f"{what[2:]:5s} built with SPIKE2IO_WHEEL={target}")


# ----------------------------------------------------------------------
# Verify
# ----------------------------------------------------------------------

def expected_counts() -> tuple[int, int]:
    """What the Windows wheel should contain, derived from the source tree."""
    n_pyd = len(list((HERE / "ced").glob("*.pyd")))
    x64 = HERE / "ced" / "x64"
    n_x64 = sum(1 for p in x64.iterdir()
                if p.suffix.lower() in (".dll", ".h", ".lib", ".m"))
    return n_pyd, n_x64


def wheel_facts(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        meta = next(n for n in names if n.endswith(".dist-info/METADATA"))
        text = z.read(meta).decode()
        wheel = z.read(meta.replace("METADATA", "WHEEL")).decode()
    def field(src, key):
        for line in src.splitlines():
            if line.startswith(key + ":"):
                return line.split(":", 1)[1].strip()
        return None
    return {
        "pyd": sum(1 for n in names if n.endswith(".pyd")),
        "x64": sum(1 for n in names if "/x64/" in n),
        "x86": sum(1 for n in names if "/x86/" in n),
        "requires_python": field(text, "Requires-Python"),
        "version": field(text, "Version"),
        "tag": field(wheel, "Tag"),
    }


def verify(version: str, py: Path) -> None:
    step("Verifying artifacts")
    n_pyd, n_x64 = expected_counts()

    win = DIST / f"{PROJECT}-{version}-py3-none-win_amd64.whl"
    any_ = DIST / f"{PROJECT}-{version}-py3-none-any.whl"
    sdist = DIST / f"{PROJECT}-{version}.tar.gz"

    for p in (win, any_, sdist):
        if not p.is_file():
            raise Fail(f"missing artifact: {p.name}")
    if len(list(DIST.iterdir())) != 3:
        raise Fail(f"dist/ should hold exactly 3 files, found: "
                   f"{[p.name for p in DIST.iterdir()]}")
    ok("all three artifacts present, nothing stale in dist/")

    # -- Windows wheel: must carry the binaries -------------------------
    w = wheel_facts(win)
    checks = [
        (w["version"] == version, f"version {w['version']} != {version}"),
        (w["tag"] == "py3-none-win_amd64", f"tag is {w['tag']}"),
        (w["requires_python"] == ">=3.9", f"Requires-Python {w['requires_python']}"),
        (w["pyd"] == n_pyd, f"{w['pyd']} .pyd, expected {n_pyd}"),
        (w["x64"] == n_x64, f"{w['x64']} x64 files, expected {n_x64}"),
        (w["x86"] == 0, f"{w['x86']} x86 files, expected 0"),
    ]
    for good, why in checks:
        if not good:
            raise Fail(f"windows wheel: {why}")
    ok(f"windows wheel: {n_pyd} extensions, {n_x64} x64 files, "
       f"{w['requires_python']}, {w['tag']}")

    # -- 'any' wheel: must carry NO binaries ----------------------------
    # This is the check that catches build/lib contamination.
    a = wheel_facts(any_)
    checks = [
        (a["version"] == version, f"version {a['version']} != {version}"),
        (a["tag"] == "py3-none-any", f"tag is {a['tag']}"),
        (a["requires_python"] == ">=3.14", f"Requires-Python {a['requires_python']}"),
        (a["pyd"] == 0, f"contains {a['pyd']} .pyd files -- build/lib was contaminated"),
        (a["x64"] == 0, f"contains {a['x64']} x64 DLLs -- build/lib was contaminated"),
        (a["x86"] == 0, f"contains {a['x86']} x86 files"),
    ]
    for good, why in checks:
        if not good:
            raise Fail(f"any wheel: {why}")
    ok(f"any wheel: no binaries, {a['requires_python']}, {a['tag']}")

    # -- sdist ----------------------------------------------------------
    with tarfile.open(sdist) as t:
        names = t.getnames()
    for pattern, label in (("/x86/", "32-bit DLLs"),
                           ("/docs/", "docs directory"),
                           ("test_code", "test scripts")):
        if any(pattern in n for n in names):
            raise Fail(f"sdist unexpectedly contains {label}")
    if not any(n.endswith(".pyd") for n in names):
        raise Fail("sdist is missing the prebuilt extensions")
    ok("sdist: extensions present, no x86 / docs / tests")

    # -- twine's own metadata and README-rendering checks ---------------
    run([str(py), "-m", "twine", "check", *[str(p) for p in DIST.iterdir()]])
    ok("twine check passed on all three")


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build and verify the spike2io release artifacts.")
    ap.add_argument("--no-venv", action="store_true",
                    help="use this interpreter's build/twine instead of a venv")
    ap.add_argument("--keep-venv", action="store_true",
                    help="do not delete the throwaway venv (for debugging)")
    args = ap.parse_args()

    tmp: Path | None = None
    try:
        version = read_version()
        preflight(version)

        if args.no_venv:
            py = Path(sys.executable)
            for mod in ("build", "twine"):
                try:
                    __import__(mod)
                except ImportError:
                    raise Fail(f"--no-venv needs {mod}: "
                               f"pip install build twine")
            ok("using the current interpreter's build tooling")
        else:
            tmp = Path(tempfile.mkdtemp(prefix="spike2io-release-"))
            py = make_venv(tmp)

        build_all(py, version)
        verify(version, py)

    except Fail as exc:
        print(f"\n\033[31mFAILED\033[0m: {exc}" if sys.stdout.isatty()
              else f"\nFAILED: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    finally:
        # Always tidy the source tree, whatever happened above.
        clean_intermediates()
        if tmp is not None and not args.keep_venv:
            shutil.rmtree(tmp, ignore_errors=True)
        elif tmp is not None:
            print(f"\n(venv kept at {tmp})")

    step("Ready to upload")
    for p in sorted(DIST.iterdir()):
        print(f"    {p.name:46s} {p.stat().st_size / 1e6:5.2f} MB")
    print(f"""
Nothing has been published. Run these yourself, in this order:

    # 1. dry run on TestPyPI (separate account and token)
    py -m twine upload --repository testpypi dist/*

    # 2. the real thing -- {version} can never be reused afterwards
    py -m twine upload dist/*

Username is __token__ and the password is your API token.
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
