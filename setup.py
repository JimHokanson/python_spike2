# -*- coding: utf-8 -*-
"""
Packaging configuration for spike2io.

NOTE ON NAMES
-------------
* PyPI distribution name  : "spike2io"  ->  pip install spike2io
* Importable package name : "ced"       ->  import ced

NOTE ON PLATFORMS
-----------------
The package reads Spike2 files through one of two backends:

  ceds64   Bundled here: prebuilt CFFI extensions plus CED's SON64 DLLs.
           Windows x64 only, CPython 3.9-3.14 (one .pyd per version).
  sonpy    CED's own package, an optional extra. It publishes Windows
           wheels for 3.9-3.14 but macOS/Linux wheels for **3.14 only**,
           and that is what bounds this package away from Windows.

Two wheels are therefore published from this one project, so that the
Windows binaries are only downloaded by people who can run them and each
platform advertises the Python versions that actually work there:

  spike2io-X.Y.Z-py3-none-win_amd64.whl    Requires-Python >=3.9
      Ships the extensions and DLLs. Nothing else to install.

  spike2io-X.Y.Z-py3-none-any.whl          Requires-Python >=3.14
      No binaries. For macOS/Linux, reading through sonpy.

Build both (from a clean tree):

    SPIKE2IO_WHEEL=windows python -m build --wheel
    SPIKE2IO_WHEEL=any     python -m build --wheel
    python -m build --sdist

The 32-bit ced/x86 directory is deliberately NOT distributed: every
prebuilt extension is win_amd64, so a 32-bit interpreter could never load
those DLLs. The files stay in the repository for anyone who later builds a
32-bit extension from ced/cffi_build.py.
"""

import os
import re
from pathlib import Path

from setuptools import find_packages, setup

HERE = Path(__file__).parent.resolve()

# Which of the two wheels to build; see the module docstring. Defaults to
# the Windows wheel so a bare `python -m build` still produces the binary
# distribution rather than silently dropping it.
WHEEL = os.environ.get("SPIKE2IO_WHEEL", "windows").lower()
if WHEEL not in ("windows", "any"):
    raise SystemExit(
        f"SPIKE2IO_WHEEL must be 'windows' or 'any', got {WHEEL!r}")
WINDOWS_WHEEL = WHEEL == "windows"


def read_long_description() -> str:
    readme = HERE / "README.md"
    if readme.exists():
        return readme.read_text(encoding="utf-8")
    return "Python reader for CED Spike2 (.smr/.smrx) files via the SON64 library."


def read_version() -> str:
    """
    Single source of truth is ced/__init__.py, read textually so that
    building does not require numpy (which importing the package would).
    """
    text = (HERE / "ced" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.M)
    if match is None:
        raise SystemExit("could not find __version__ in ced/__init__.py")
    return match.group(1)


setup(
    # ---- Identity ---------------------------------------------------------
    name="spike2io",
    version=read_version(),
    description=(
        "Read CED Spike2 (.smr/.smrx) data files in Python via the "
        "native SON64 library."
    ),
    long_description=read_long_description(),
    long_description_content_type="text/markdown",
    # ---- Authorship / links ----------------------------------------------
    author="Jim Hokanson",
    author_email="jim.hokanson@gmail.com",
    url="https://github.com/JimHokanson/python_spike2",
    project_urls={
        "Source": "https://github.com/JimHokanson/python_spike2",
        "Issues": "https://github.com/JimHokanson/python_spike2/issues",
    },
    license="MIT",
    # ---- What to include --------------------------------------------------
    # The importable package is "ced". x64/ is a data directory (no
    # __init__.py) holding native DLLs, shipped via package_data rather
    # than as a Python sub-package.
    #
    # package_data governs the wheel; MANIFEST.in governs the sdist. Note
    # include_package_data is deliberately NOT set: it would fold the
    # MANIFEST.in contents into the wheel, which would put the Windows
    # binaries back into the 'any' wheel.
    packages=find_packages(include=["ced", "ced.*"]),
    package_data={
        "ced": [
            "*.pyd",          # prebuilt CFFI extensions (cp39-cp314, win_amd64)
            "*.c",            # generated C source (for rebuilding the extension)
            "x64/*.dll",      # 64-bit native libraries (loaded at runtime)
            "x64/*.h",        # headers (needed only to rebuild from source)
            "x64/*.lib",
            "x64/*.m",        # MATLAB prototype reference files
        ],
    } if WINDOWS_WHEEL else {},
    # Binary DLLs are loaded from disk via os.add_dll_directory()/__file__,
    # so the package must be installed unzipped.
    zip_safe=False,
    # ---- Dependencies -----------------------------------------------------
    # Windows ships the ceds64 backend and supports every version we have a
    # .pyd for. Elsewhere the only backend is sonpy, whose macOS/Linux
    # wheels exist for CPython 3.14 only.
    python_requires=">=3.9" if WINDOWS_WHEEL else ">=3.14",
    install_requires=[
        "numpy",
        # The out-of-line CFFI extension imports _cffi_backend at runtime,
        # which is provided by the cffi package. Only the bundled ceds64
        # backend needs it, and that backend is Windows-only.
        'cffi>=1.0.0; platform_system=="Windows"',
    ],
    extras_require={
        # CED's own binding. The only backend off Windows, and a usable
        # alternative on Windows.
        "sonpy": ["sonpy"],
        # Only needed for the .plot() helpers (imported lazily).
        "plot": ["matplotlib"],
    },
    # ---- Metadata ---------------------------------------------------------
    # Kept identical across both wheels so the PyPI page describes the
    # project as a whole; the per-platform limits are expressed by
    # Requires-Python and the wheel tags above.
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: MacOS",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Topic :: Scientific/Engineering",
    ],
    keywords=["spike2", "ced", "son64", "smrx", "electrophysiology", "neuroscience"],
    # The Windows wheel carries win_amd64 binaries, so tag it accordingly
    # rather than letting a pure-Python build claim py3-none-any.
    options={"bdist_wheel": {"plat_name": "win_amd64"}} if WINDOWS_WHEEL else {},
)
