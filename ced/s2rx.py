# -*- coding: utf-8 -*-
"""
Created on Mon Jun  1 21:34:08 2026

@author: jimho

Python translation of NeuralDataFormats/matlab_spike2 s2rx_file class and
associated sub-classes from the ced.s2rx namespace.

Original MATLAB source:
  +ced/@s2rx_file/s2rx_file.m
  +ced/+s2rx/XInfo.m  (inferred from usage + XML schema comment)
  +ced/+s2rx/VCur.m   (inferred from XML schema comment)
  +ced/+s2rx/HCur.m   (inferred from XML schema comment)

The .s2rx file is an XML sidecar file that accompanies a Spike2 .smrx
recording.  It stores view-level metadata such as cursor positions.

XML schema (from original comment block):
    CEDResources
      DocTime
        ChanProc
        View
          WPlace
          Font
          Chan
          FitParam
          C
          XInfo
            VCur: id, LabMode, LabPos, Num, AMod
            ActC: id
            HCur: id, Pos, LabMode, LabPos, Num
          ChOrder
          CursVals
          CursRegs
          OvDraw3d
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import xml.etree.ElementTree as ET


# ---------------------------------------------------------------------------
# Attribute helpers
# ---------------------------------------------------------------------------
# MATLAB reads these files with readstruct(), which converts numeric XML
# attributes to doubles and leaves absent ones as NaN. The equivalent here is
# a float or None -- None rather than NaN so that a missing cursor position
# cannot propagate silently through arithmetic.

def _attr(d: dict, *names: str):
    """
    First present value among *names*, checking both the bare attribute
    name and the '@'-prefixed form produced by _elem_to_dict().
    """
    for name in names:
        for key in (name, f"@{name}"):
            if key in d and d[key] is not None:
                return d[key]
    return None


def _as_float(value) -> Optional[float]:
    """Numeric attribute value, or None if absent/unparseable."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _elem_attrib(elem: ET.Element) -> dict:
    """Attributes of *elem*, plus any child elements keyed by tag."""
    d: dict = dict(elem.attrib)
    for child in elem:
        d[child.tag] = child.text
    return d


# ---------------------------------------------------------------------------
# s2rx.VCur  –  Vertical (time-axis) cursor
# ---------------------------------------------------------------------------

@dataclass
class VCur:
    """
    One vertical cursor from the XInfo block of a .s2rx file.

    This is the Python equivalent of a single row of the table held by
    MATLAB's ``ced.s2rx.xinfo.Vcursor``; the list of them on
    :class:`XInfo` is the whole table. Every field is the parsed numeric
    attribute value, or None when the attribute is absent.

    Attributes
    ----------
    id : Optional[float]
        Cursor identifier.
    lab_mode : Optional[float]
        Label display mode.
    lab_pos : Optional[float]
        Label placement along the axis, as a fraction. NOT a time --
        this is where the label is drawn, and is typically 0.2.
    num : Optional[float]
        Cursor number / index.
    pos : Optional[float]
        Cursor position in seconds. This is the cursor's time.
    a_mode : Optional[float]
        Amplitude mode.
    """

    id: Optional[float] = None
    lab_mode: Optional[float] = None
    lab_pos: Optional[float] = None
    num: Optional[float] = None
    pos: Optional[float] = None
    a_mode: Optional[float] = None

    @classmethod
    def from_dict(cls, d: dict) -> "VCur":
        """Construct a VCur from a dict of XML attribute values."""
        return cls(
            id=_as_float(_attr(d, "id")),
            lab_mode=_as_float(_attr(d, "LabMode")),
            lab_pos=_as_float(_attr(d, "LabPos")),
            num=_as_float(_attr(d, "Num")),
            pos=_as_float(_attr(d, "Pos")),
            # MATLAB reads 'AMode'; the schema comment below says 'AMod'.
            # Neither appears in any example file, so accept both.
            a_mode=_as_float(_attr(d, "AMode", "AMod")),
        )

    @classmethod
    def from_xml_element(cls, elem: ET.Element) -> "VCur":
        """Construct a VCur from an xml.etree.ElementTree Element."""
        return cls.from_dict(_elem_attrib(elem))


# ---------------------------------------------------------------------------
# s2rx.HCur  –  Horizontal (amplitude-axis) cursor
# ---------------------------------------------------------------------------

@dataclass
class HCur:
    """
    One horizontal cursor from the XInfo block.

    Has no counterpart in the MATLAB library, which only models vertical
    cursors; the field conventions follow :class:`VCur`.

    Attributes
    ----------
    id : Optional[float]
        Cursor identifier.
    pos : Optional[float]
        Cursor position in the channel's amplitude units.
    lab_mode : Optional[float]
        Label display mode.
    lab_pos : Optional[float]
        Label placement along the axis, as a fraction (not an amplitude).
    num : Optional[float]
        Cursor number / index.
    """

    id: Optional[float] = None
    pos: Optional[float] = None
    lab_mode: Optional[float] = None
    lab_pos: Optional[float] = None
    num: Optional[float] = None

    @classmethod
    def from_dict(cls, d: dict) -> "HCur":
        """Construct an HCur from a dict of XML attribute values."""
        return cls(
            id=_as_float(_attr(d, "id")),
            pos=_as_float(_attr(d, "Pos")),
            lab_mode=_as_float(_attr(d, "LabMode")),
            lab_pos=_as_float(_attr(d, "LabPos")),
            num=_as_float(_attr(d, "Num")),
        )

    @classmethod
    def from_xml_element(cls, elem: ET.Element) -> "HCur":
        return cls.from_dict(_elem_attrib(elem))


# ---------------------------------------------------------------------------
# s2rx.XInfo  –  Extended view information block
# ---------------------------------------------------------------------------

@dataclass
class XInfo:
    """
    Represents the XInfo element inside a Spike2 .s2rx XML file.

    The XInfo block holds vertical cursors (VCur), active channel (ActC)
    and horizontal cursors (HCur).

    ``vcursors`` is the equivalent of MATLAB's ``x_info.vcursor.data``
    table: one entry per cursor rather than one table with a row each.
    An empty list means the file declared no cursors of that kind.

    Attributes
    ----------
    vcursors : list[VCur]
        All vertical cursors, in document order.
    act_c : Optional[str]
        Active channel id (from ActC element).
    hcursors : list[HCur]
        All horizontal cursors, in document order.
    """

    vcursors: list = field(default_factory=list)
    act_c: Optional[str] = None
    hcursors: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "XInfo":
        """
        Construct an XInfo from a nested dictionary as produced by
        xml.etree.ElementTree or a similar XML-to-dict parser.

        ``d`` is expected to be the dictionary representation of the
        ``<XInfo>`` element.
        """
        obj = cls()

        def _as_list(raw):
            # A single occurrence comes through as one dict, several as
            # a list of dicts.
            if raw is None:
                return []
            return raw if isinstance(raw, list) else [raw]

        obj.vcursors = [VCur.from_dict(v) for v in _as_list(d.get("VCur"))]
        obj.hcursors = [HCur.from_dict(h) for h in _as_list(d.get("HCur"))]

        # ---- active channel ------------------------------------------
        act_c_raw = d.get("ActC")
        if act_c_raw is not None:
            if isinstance(act_c_raw, dict):
                obj.act_c = str(act_c_raw.get("id", act_c_raw.get("@id", "")))
            else:
                obj.act_c = str(act_c_raw)

        return obj

    @classmethod
    def from_xml_element(cls, elem: ET.Element) -> "XInfo":
        """Construct an XInfo by parsing an xml.etree.ElementTree Element."""
        obj = cls()

        obj.vcursors = [VCur.from_xml_element(e) for e in elem.findall("VCur")]
        obj.hcursors = [HCur.from_xml_element(e) for e in elem.findall("HCur")]

        # ---- active channel ------------------------------------------
        act_c_elem = elem.find("ActC")
        if act_c_elem is not None:
            obj.act_c = act_c_elem.get("id", act_c_elem.text)

        return obj


# ---------------------------------------------------------------------------
# Helpers for XML → dict (mirrors MATLAB's readstruct / xmlread behaviour)
# ---------------------------------------------------------------------------

def _elem_to_dict(elem: ET.Element) -> dict:
    """
    Recursively convert an ElementTree Element into a nested dict.

    Attributes become top-level keys (prefixed with '@' to distinguish
    from child elements, matching common XML-to-dict conventions).
    Text content is stored under the key '#text'.
    Child elements with the same tag are collected into a list.
    """
    d: dict = {}

    # Store XML attributes
    for k, v in elem.attrib.items():
        d[f"@{k}"] = v
        # Also store without prefix for easier access
        d[k] = v

    # Store child elements
    children: dict = {}
    for child in elem:
        tag = child.tag
        child_dict = _elem_to_dict(child)
        if tag in children:
            existing = children[tag]
            if isinstance(existing, list):
                existing.append(child_dict)
            else:
                children[tag] = [existing, child_dict]
        else:
            children[tag] = child_dict

    d.update(children)

    # Text content (stripped)
    text = (elem.text or "").strip()
    if text:
        d["#text"] = text

    return d


# ---------------------------------------------------------------------------
# S2rxFile  –  Main class (ced.s2rx_file)
# ---------------------------------------------------------------------------

class S2rxFile:
    """
    Python equivalent of MATLAB's ``ced.s2rx_file`` class.

    Parses a Spike2 resource (.s2rx) XML file and exposes view-level
    metadata, most notably cursor positions.

    Parameters
    ----------
    file_path : str
        Path to the .s2rx XML file.

    Attributes
    ----------
    file_path : str
        Path supplied to the constructor.
    x_info : Optional[XInfo]
        Parsed XInfo object, or None if not present in the file.

    Examples
    --------
    >>> f = S2rxFile("recording.s2rx")
    >>> positions = f.get_vertical_cursor_positions()
    >>> print(positions)   # list of float times (seconds)
    """

    def __init__(self, file_path: str) -> None:
        self.file_path: str = file_path
        self.x_info: Optional[XInfo] = None

        tree = ET.parse(file_path)
        root = tree.getroot()

        # Navigate:  root → DocTime → View → XInfo
        # (mirrors MATLAB: x.DocTime.View.XInfo)
        x_info_elem: Optional[ET.Element] = None
        try:
            doc_time = root.find("DocTime")
            if doc_time is None:
                # Some files may have DocTime as the root itself
                doc_time = root if root.tag == "DocTime" else None
            if doc_time is not None:
                view_elems = doc_time.findall("View")
                if view_elems:
                    # MATLAB takes the first when multiple views exist
                    view = view_elems[0]
                    x_info_elem = view.find("XInfo")
        except Exception:
            x_info_elem = None

        if x_info_elem is not None:
            self.x_info = XInfo.from_xml_element(x_info_elem)

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def get_vertical_cursor_positions(self) -> list:
        """
        Return the times of all vertical cursors, in seconds.

        Counterpart of MATLAB's ``getVerticalCursorPositions``, which
        returns the whole ``vcursor.data`` table. Here the table itself is
        ``self.x_info.vcursors``, so this method returns just the ``Pos``
        column -- what its name promises.

        Returns
        -------
        list of float
            Cursor times in seconds. Cursors with no Pos attribute are
            omitted; an empty list means there are no vertical cursors.
        """
        if self.x_info is None:
            return []
        return [c.pos for c in self.x_info.vcursors if c.pos is not None]

    def get_horizontal_cursor_positions(self) -> list:
        """
        Return the positions of all horizontal cursors, in the amplitude
        units of the channel they sit on.

        Returns
        -------
        list of float
            Cursor positions. Cursors with no Pos attribute are omitted;
            an empty list means there are no horizontal cursors.
        """
        if self.x_info is None:
            return []
        return [c.pos for c in self.x_info.hcursors if c.pos is not None]

    def __repr__(self) -> str:
        vcur_count = len(self.x_info.vcursors) if self.x_info else 0
        hcur_count = len(self.x_info.hcursors) if self.x_info else 0
        return (
            f"S2rxFile(file_path={self.file_path!r}, "
            f"vcursors={vcur_count}, hcursors={hcur_count})"
        )


