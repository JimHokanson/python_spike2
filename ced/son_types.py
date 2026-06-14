# -*- coding: utf-8 -*-
"""
Shared SON/Spike2 record types used by all backends.

This module intentionally contains only backend-neutral Python types.
Backend-specific conversion code, such as cffi S64Marker conversion,
belongs in the backend modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Tuple, Union

import numpy as np


class ChanType(IntEnum):
    """
    Channel type codes returned by chan_type().

    These values match the CED SON channel type values used by both
    the ceds64 backend and sonpy.
    """

    OFF = 0
    ADC = 1
    EVENT_FALL = 2
    EVENT_RISE = 3
    EVENT_BOTH = 4
    MARKER = 5
    ADC_MARK = 6
    REAL_MARK = 7
    TEXT_MARK = 8
    REAL_WAVE = 9


@dataclass
class CEDMarker:
    """A basic marker: 64-bit timestamp plus four 8-bit codes."""

    time: int = 0
    code1: int = 0
    code2: int = 0
    code3: int = 0
    code4: int = 0

    @property
    def codes(self) -> Tuple[int, int, int, int]:
        return (self.code1, self.code2, self.code3, self.code4)


@dataclass
class CEDTextMark(CEDMarker):
    """A marker with attached text data."""

    data: str = ""


@dataclass
class CEDRealMark(CEDMarker):
    """A marker with attached float32 data, shaped as rows × cols."""

    data: np.ndarray = field(
        default_factory=lambda: np.empty((0, 0), dtype=np.float32)
    )


@dataclass
class CEDWaveMark(CEDMarker):
    """A marker with attached int16 waveform data, shaped as rows × cols."""

    data: np.ndarray = field(
        default_factory=lambda: np.empty((0, 0), dtype=np.int16)
    )


CEDExtMark = Union[CEDTextMark, CEDRealMark, CEDWaveMark]
CEDAnyMark = Union[CEDMarker, CEDTextMark, CEDRealMark, CEDWaveMark]