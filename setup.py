# -*- coding: utf-8 -*-
"""
Packaging configuration for spike2io.

NOTE ON NAMES
-------------
* PyPI distribution name : "spike2io"   ->  pip install python-spike2
* Importable package name : "ced"            ->  import ced
  (The short name "ced" is already taken on PyPI, so the distribution is
  published as "python-spike2" while the import name stays "ced".)

NOTE ON PLATFORM
----------------
This project wraps Cambridge Electronic Design's native SON64 library and
ships prebuilt CFFI extensions + Windows DLLs. It therefore only runs on
**Windows (amd64)**, and prebuilt extensions are currently provided for
**CPython 3.9 and 3.13** only. See the README for building from source for
other interpreter versions.
"""

from pathlib import Path

from setuptools import find_packages, setup

HERE = Path(__file__).parent.resolve()


def read_long_description() -> str:
    readme = HERE / "README.md"
    if readme.exists():
        return readme.read_text(encoding="utf-8")
    return "Python reader for CED Spike2 (.smr/.smrx) files via the SON64 library."


setup(
    # ---- Identity ---------------------------------------------------------
    name="spike2io",
    version="0.1.0",
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
    # The importable package is "ced". x64/ and x86/ are data directories
    # (no __init__.py) holding native DLLs/headers, so they are shipped via
    # package_data rather than as Python sub-packages.
    packages=find_packages(include=["ced", "ced.*"]),
    package_data={
        "ced": [
            "*.pyd",          # prebuilt CFFI extensions (cp39, cp313 - win_amd64)
            "*.c",            # generated C source (for rebuilding the extension)
            "x64/*.dll",      # 64-bit native libraries (loaded at runtime)
            "x64/*.h",        # headers (needed only to rebuild from source)
            "x64/*.lib",
            "x64/*.m",        # MATLAB prototype reference files
            "x86/*.dll",      # 32-bit native libraries
            "x86/*.h",
            "x86/*.lib",
            "x86/*.m",
        ],
    },
    include_package_data=True,
    # Binary DLLs are loaded from disk via os.add_dll_directory()/__file__,
    # so the package must be installed unzipped.
    zip_safe=False,
    # ---- Dependencies -----------------------------------------------------
    python_requires=">=3.9",
    install_requires=[
        "numpy",
        # The out-of-line CFFI extension imports _cffi_backend at runtime,
        # which is provided by the cffi package.
        "cffi>=1.0.0",
    ],
    extras_require={
        # Optional: only needed for the .plot() helpers (imported lazily).
        "plot": ["matplotlib"],
    },
    # ---- Metadata ---------------------------------------------------------
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.13",
        "Topic :: Scientific/Engineering",
    ],
    keywords=["spike2", "ced", "son64", "smrx", "electrophysiology", "neuroscience"],
)
