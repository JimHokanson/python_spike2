# -*- coding: utf-8 -*-
"""
test_backend_parity.py -- confirm the *sonpy* backend reads the same data as the
*ceds64* backend.

This loads the same example ``.smr`` / ``.smrx`` files with both backends
(``ced.read_file(path, backend="ceds64")`` and ``backend="sonpy"``) and asserts
that the user-facing results are equal: file metadata, the discovered channel
list, channel metadata, and -- most importantly -- the actual data
(waveform segments, event/level times, markers, extended markers).

Where the two backends are *known* to diverge, the difference is encoded
explicitly here (search for "KNOWN DIVERGENCE") rather than silently ignored, so
that this file doubles as living documentation of the sonpy backend's caveats.

Running
-------
requires specification of location of example directory location - see below
source: https://github.com/JimHokanson/spike2_example_files

Requires an interpreter that has **both** backends available -- i.e. numpy +
the bundled ``_ceds64_cffi`` extension (ceds64) **and** an importable
``sonpy`` (CED's wheel; only some Python versions have a working build). As of
this writing that is Python 3.14 with ``sonpy==1.9.12`` installed.

    # with pytest (preferred):
    py -3.14 -m pytest test_code/test_backend_parity.py -v

    # or as a plain script (no pytest needed):
    py -3.14 test_code/test_backend_parity.py

The example files are located via the ``SPIKE2_EXAMPLE_DIR`` environment
variable if set, otherwise a short list of default locations is tried. If
neither the files nor a backend is available the tests skip rather than fail.
"""

from __future__ import annotations

import os
import sys
import math

import numpy as np

# --------------------------------------------------------------------------
# Make the package importable when run directly from the repo.
# --------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_THIS_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# --------------------------------------------------------------------------
# Locate the example-files directory.
# --------------------------------------------------------------------------
def _find_example_dir():
    candidates = []
    env = os.environ.get("SPIKE2_EXAMPLE_DIR")
    if env:
        candidates.append(env)
    candidates += [
        r"E:\repos\data\spike2_example_files\files",
        r"C:\repos\data\spike2_example_files\files",
        os.path.join(_REPO_ROOT, "..", "spike2_example_files", "files"),
        os.path.join(_REPO_ROOT, "test_code", "files"),
    ]
    for c in candidates:
        if c and os.path.isdir(c):
            return os.path.abspath(c)
    return None


EXAMPLE_DIR = _find_example_dir()


# --------------------------------------------------------------------------
# Backend availability.
# --------------------------------------------------------------------------
def _have_backend(backend: str) -> bool:
    try:
        import ced  # noqa: F401
    except Exception:
        return False
    try:
        if backend == "sonpy":
            import sonpy  # noqa: F401
            return True
        from ced import ffi_ceds64  # noqa: F401  (the ceds64 cffi extension)
        return True
    except Exception:
        return False


HAVE_CEDS64 = _have_backend("ceds64")
HAVE_SONPY = _have_backend("sonpy")
BOTH_BACKENDS = HAVE_CEDS64 and HAVE_SONPY


# --------------------------------------------------------------------------
# Files to compare with BOTH backends (parity).
#
# Every file listed here must be openable by both backends. example1.smr /
# example2.smr are deliberately NOT here: the bundled ceds64 DLL returns error
# -13 on them while sonpy opens them fine, so they are exercised as sonpy-only
# smoke tests below instead of as a parity comparison.
# --------------------------------------------------------------------------
CANDIDATE_FILES = [
    "Demo.smr",          # ADC + events
    "Demo1.smr",         # ADC with gaps (multiple segments) + event rise
    "Demo2.smr",         # exercises the file-comment NUL-truncation path
    "biomech0deg.smr",
    "biomech5deg.smr",
    "data.smr",
    "motor_units.smr",
    "physiology.smr",
    "tremor_kinetic.smr",
    "tremor_mvc_ext.smr",
    "tremor_mvc_flex.smr",
    "tremor_postural.smr",
    "Demo_Jim.smrx",     # rich: event fall/both, marker, textmark, realmark, wavemark
]

# Files the ceds64 DLL cannot open (error -13) but sonpy can: smoke-tested
# with the sonpy backend only.
SONPY_ONLY_FILES = [
    "example1.smr",
    "example2.smr",
]


def _files_in(names):
    if EXAMPLE_DIR is None:
        return []
    out = []
    for fn in names:
        p = os.path.join(EXAMPLE_DIR, fn)
        if os.path.isfile(p):
            out.append(p)
    return out


def _available_files():
    return _files_in(CANDIDATE_FILES)


# Floating point comparison tolerances.
RTOL = 1e-6
ATOL = 1e-9


# ==========================================================================
# Comparison helpers -- each appends human-readable strings to ``diffs``.
# ==========================================================================
def _eq_scalar(diffs, label, a, b, tol=0.0):
    if isinstance(a, float) or isinstance(b, float):
        try:
            fa, fb = float(a), float(b)
            ok = (math.isnan(fa) and math.isnan(fb)) or abs(fa - fb) <= tol + ATOL
        except (TypeError, ValueError):
            ok = a == b
    else:
        ok = a == b
    if not ok:
        diffs.append(f"{label}: ceds64={a!r} sonpy={b!r}")


def _eq_array(diffs, label, a, b):
    a = np.asarray(a)
    b = np.asarray(b)
    if a.shape != b.shape:
        diffs.append(f"{label}: shape ceds64={a.shape} sonpy={b.shape}")
        return
    if a.size == 0:
        return
    if np.issubdtype(a.dtype, np.floating) or np.issubdtype(b.dtype, np.floating):
        if not np.allclose(a.astype(np.float64), b.astype(np.float64),
                           rtol=RTOL, atol=ATOL, equal_nan=True):
            d = np.abs(a.astype(np.float64) - b.astype(np.float64))
            diffs.append(f"{label}: max|diff|={d.max():.3g} at index {int(d.argmax())}")
    else:
        if not np.array_equal(a, b):
            n = int((a != b).sum())
            diffs.append(f"{label}: {n}/{a.size} elements differ")


# ==========================================================================
# The actual comparison of one file across the two backends.
# ==========================================================================
def compare_file(path):
    """Return a list of human-readable difference strings (empty == parity)."""
    import ced

    diffs = []
    fa = ced.read_file(path, backend="ceds64")
    try:
        fb = ced.read_file(path, backend="sonpy")
    except Exception:
        fa.close()
        raise

    try:
        # ---- File-level metadata -------------------------------------
        _eq_scalar(diffs, "file.version", fa.version, fb.version)
        _eq_scalar(diffs, "file.time_base", float(fa.time_base), float(fb.time_base))
        _eq_scalar(diffs, "file.n_ticks", float(fa.n_ticks), float(fb.n_ticks))
        _eq_scalar(diffs, "file.n_seconds", float(fa.n_seconds), float(fb.n_seconds))
        _eq_scalar(diffs, "file.file_size", fa.file_size, fb.file_size)
        _eq_scalar(diffs, "file.start_datetime", fa.start_datetime, fb.start_datetime)
        _eq_scalar(diffs, "file.app_id", tuple(fa.app_id), tuple(fb.app_id))
        _eq_scalar(diffs, "file.comments", tuple(fa.comments), tuple(fb.comments))

        # ---- Channel discovery ---------------------------------------
        for attr in ("waveforms", "event_rises", "event_falls", "event_both",
                     "markers", "wave_markers", "real_markers", "text_markers"):
            _eq_scalar(diffs, f"len({attr})",
                       len(getattr(fa, attr)), len(getattr(fb, attr)))
        _eq_scalar(diffs, "chan_ids",
                   tuple(c.chan_id for c in fa.all_chan_objects),
                   tuple(c.chan_id for c in fb.all_chan_objects))

        # ---- Per-channel metadata ------------------------------------
        if len(fa.all_chan_objects) == len(fb.all_chan_objects):
            for ca, cb in zip(fa.all_chan_objects, fb.all_chan_objects):
                pre = f"ch{ca.chan_id}({ca.name})"
                _eq_scalar(diffs, f"{pre}.name", ca.name, cb.name)
                _eq_scalar(diffs, f"{pre}.units", ca.units, cb.units)
                _eq_scalar(diffs, f"{pre}.comment", ca.comment, cb.comment)
                _eq_scalar(diffs, f"{pre}.scale", float(ca.scale), float(cb.scale))
                _eq_scalar(diffs, f"{pre}.offset",
                           float(ca.chan_offset), float(cb.chan_offset))
                _eq_scalar(diffs, f"{pre}.y_range",
                           tuple(ca.y_range), tuple(cb.y_range))
                _eq_scalar(diffs, f"{pre}.n_ticks", int(ca.n_ticks), int(cb.n_ticks))
                _eq_scalar(diffs, f"{pre}.chan_div", ca.chan_div, cb.chan_div)
                _eq_scalar(diffs, f"{pre}.fs", float(ca.fs), float(cb.fs))

        # ---- Waveform data (segments, incl. gap splitting) -----------
        for wa, wb in zip(fa.waveforms, fb.waveforms):
            sa = wa.get_data()
            sb = wb.get_data()
            pre = f"wave[{wa.name}]"
            _eq_scalar(diffs, f"{pre}.n_segments", len(sa), len(sb))
            for i, (s1, s2) in enumerate(zip(sa, sb)):
                _eq_scalar(diffs, f"{pre}.seg{i}.first_sample",
                           s1.first_sample, s2.first_sample)
                _eq_scalar(diffs, f"{pre}.seg{i}.n_samples",
                           s1.n_samples, s2.n_samples)
                _eq_scalar(diffs, f"{pre}.seg{i}.start_time",
                           float(s1.start_time), float(s2.start_time))
                _eq_array(diffs, f"{pre}.seg{i}.data", s1.data, s2.data)
                _eq_array(diffs, f"{pre}.seg{i}.time", s1.time, s2.time)

        # ---- Event rise/fall times -----------------------------------
        for ea, eb in zip(fa.event_rises + fa.event_falls,
                          fb.event_rises + fb.event_falls):
            ra, rb = ea.get_times(), eb.get_times()
            _eq_scalar(diffs, f"evt[{ea.name}].n_events", ra.n_events, rb.n_events)
            _eq_array(diffs, f"evt[{ea.name}].times", ra.times, rb.times)

        # ---- EventBoth (level) times ---------------------------------
        for ea, eb in zip(fa.event_both, fb.event_both):
            ra, rb = ea.get_times(), eb.get_times()
            _eq_scalar(diffs, f"both[{ea.name}].n_events", ra.n_events, rb.n_events)
            _eq_array(diffs, f"both[{ea.name}].times", ra.times, rb.times)
            # start_level: the sonpy backend recovers the initial level from the
            # per-transition marker codes (ReadMarkers Code1), so it now agrees
            # with ceds64's S64ReadLevels. Assert full parity.
            _eq_scalar(diffs, f"both[{ea.name}].start_level",
                       ra.start_level, rb.start_level)

        # ---- Markers (DigMark: time + 4 codes) -----------------------
        for ma, mb in zip(fa.markers, fb.markers):
            ra, rb = ma.get_data(), mb.get_data()
            _eq_scalar(diffs, f"mark[{ma.name}].n_events", ra.n_events, rb.n_events)
            _eq_array(diffs, f"mark[{ma.name}].times", ra.times, rb.times)
            for c in ("c1", "c2", "c3", "c4"):
                _eq_array(diffs, f"mark[{ma.name}].{c}",
                          getattr(ra, c), getattr(rb, c))

        # ---- Extended markers ----------------------------------------
        # TextMark: full parity (time, codes, text).
        for ta, tb in zip(fa.text_markers, fb.text_markers):
            ra, rb = ta.get_data(), tb.get_data()
            na, ma_ = ra.n_events, ra.markers
            nb, mb_ = rb.n_events, rb.markers
            _eq_scalar(diffs, f"text[{ta.name}].n", na, nb)
            _eq_array(diffs, f"text[{ta.name}].times",
                      [m.time for m in ma_], [m.time for m in mb_])
            _eq_scalar(diffs, f"text[{ta.name}].codes",
                       [m.codes for m in ma_], [m.codes for m in mb_])
            _eq_scalar(diffs, f"text[{ta.name}].text",
                       [m.data for m in ma_], [m.data for m in mb_])

        # RealMark / WaveMark: time + codes parity. The numeric sample payload
        # is a KNOWN DIVERGENCE -- sonpy 1.9.12's RealMarker/WaveMarker expose
        # no attribute for it, so the sonpy backend returns empty .data. We
        # assert the timestamps and codes match and do NOT compare .data.
        for ma, mb in zip(fa.real_markers + fa.wave_markers,
                          fb.real_markers + fb.wave_markers):
            ra, rb = ma.get_data(), mb.get_data()
            na, la_ = ra.n_events, ra.markers
            nb, lb_ = rb.n_events, rb.markers
            _eq_scalar(diffs, f"extmark[{ma.name}].n", na, nb)
            _eq_array(diffs, f"extmark[{ma.name}].times",
                      [m.time for m in la_], [m.time for m in lb_])
            _eq_scalar(diffs, f"extmark[{ma.name}].codes",
                       [m.codes for m in la_], [m.codes for m in lb_])
    finally:
        fa.close()
        fb.close()

    return diffs


def sonpy_smoke(path):
    """
    Open a file the ceds64 DLL refuses (error -13) with the sonpy backend only
    and sanity-check that it reads. Returns a list of problem strings (empty ==
    OK). This is a capability check, not a parity comparison.
    """
    import ced

    problems = []
    f = ced.read_file(path, backend="sonpy")
    try:
        n_chans = (len(f.waveforms) + len(f.event_rises) + len(f.event_falls)
                   + len(f.event_both) + len(f.markers) + len(f.wave_markers)
                   + len(f.real_markers) + len(f.text_markers))
        if n_chans == 0:
            problems.append("no channels discovered")
        if not (f.n_seconds > 0):
            problems.append(f"non-positive duration n_seconds={f.n_seconds}")
        # Pull real data from the first waveform / event channel, if any.
        if f.waveforms:
            segs = f.waveforms[0].get_data()
            if not segs or segs[0].n_samples <= 0:
                problems.append("first waveform returned no samples")
        for ev in (f.event_rises + f.event_falls):
            r = ev.get_times()
            if r.n_events < 0:
                problems.append(f"event channel {ev.name!r} read error")
            break
    finally:
        f.close()
    return problems


# ==========================================================================
# pytest entry points
# ==========================================================================
try:
    import pytest

    _files = _available_files()
    _sonpy_only = _files_in(SONPY_ONLY_FILES)

    @pytest.mark.skipif(not BOTH_BACKENDS,
                        reason="needs both ceds64 and sonpy backends available")
    @pytest.mark.skipif(EXAMPLE_DIR is None,
                        reason="example-files dir not found (set SPIKE2_EXAMPLE_DIR)")
    @pytest.mark.skipif(not _files, reason="no candidate example files present")
    @pytest.mark.parametrize("path", _files, ids=[os.path.basename(f) for f in _files])
    def test_backends_match(path):
        diffs = compare_file(path)
        assert not diffs, (
            f"{os.path.basename(path)}: ceds64 vs sonpy differ:\n  "
            + "\n  ".join(diffs)
        )

    @pytest.mark.skipif(not HAVE_SONPY, reason="needs the sonpy backend")
    @pytest.mark.skipif(EXAMPLE_DIR is None,
                        reason="example-files dir not found (set SPIKE2_EXAMPLE_DIR)")
    @pytest.mark.skipif(not _sonpy_only, reason="no sonpy-only example files present")
    @pytest.mark.parametrize("path", _sonpy_only,
                             ids=[os.path.basename(f) for f in _sonpy_only])
    def test_sonpy_only_reads(path):
        problems = sonpy_smoke(path)
        assert not problems, (
            f"{os.path.basename(path)}: sonpy read problems:\n  "
            + "\n  ".join(problems)
        )

except ImportError:
    pytest = None


# ==========================================================================
# Plain-script entry point (no pytest required)
# ==========================================================================
def _main():
    if EXAMPLE_DIR is None:
        print("SKIP: example-files directory not found "
              "(set SPIKE2_EXAMPLE_DIR).")
        return 0
    if not BOTH_BACKENDS:
        print(f"SKIP: need both backends (ceds64={HAVE_CEDS64}, sonpy={HAVE_SONPY}).")
        return 0

    files = _available_files()
    if not files:
        print(f"SKIP: no candidate files found in {EXAMPLE_DIR}.")
        return 0

    print(f"Comparing {len(files)} file(s) from {EXAMPLE_DIR}\n")
    total = 0
    for p in files:
        diffs = compare_file(p)
        if diffs:
            total += len(diffs)
            print(f"[DIFF] {os.path.basename(p)}")
            for d in diffs:
                print(f"         {d}")
        else:
            print(f"[ OK ] {os.path.basename(p)}")

    # sonpy-only files (ceds64 DLL can't open them).
    sonpy_only = _files_in(SONPY_ONLY_FILES)
    if sonpy_only and HAVE_SONPY:
        print("\nsonpy-only smoke tests (ceds64 cannot open these):")
        for p in sonpy_only:
            problems = sonpy_smoke(p)
            if problems:
                total += len(problems)
                print(f"[FAIL] {os.path.basename(p)}: " + "; ".join(problems))
            else:
                print(f"[ OK ] {os.path.basename(p)}")

    print()
    if total:
        print(f"FAILED: {total} problem(s) found.")
        return 1
    print("PASSED: backends agree on every compared field; sonpy-only files read OK.")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
