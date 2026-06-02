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
# s2rx.VCur  –  Vertical (time-axis) cursor
# ---------------------------------------------------------------------------

@dataclass
class VCur:
    """
    Represents a vertical cursor stored in the XInfo block of a .s2rx file.

    Attributes
    ----------
    id : str
        Cursor identifier (attribute on the XML element).
    lab_mode : Optional[str]
        Label display mode.
    lab_pos : Optional[str]
        Label position.
    num : Optional[str]
        Cursor number / index.
    a_mod : Optional[str]
        Amplitude mode.
    data : Optional[float]
        Parsed numeric position of the cursor (seconds).  Derived from
        LabPos when it contains a float string, or from Num; the exact
        field used depends on what the file contains.
    """

    id: str = ""
    lab_mode: Optional[str] = None
    lab_pos: Optional[str] = None
    num: Optional[str] = None
    a_mod: Optional[str] = None
    data: Optional[float] = None

    @classmethod
    def from_dict(cls, d: dict) -> "VCur":
        """
        Construct a VCur from a dictionary of XML attributes/child-element
        values (keys are the XML attribute / element names).

        The MATLAB code accesses ``x_info.vcursor.data``, so we try to
        populate ``data`` from any numeric field available.
        """
        obj = cls()
        obj.id = str(d.get("id", d.get("@id", "")))
        obj.lab_mode = d.get("LabMode")
        obj.lab_pos = d.get("LabPos")
        obj.num = d.get("Num")
        obj.a_mod = d.get("AMod")

        # Try to derive a float 'data' value from LabPos, then Num.
        for candidate_key in ("LabPos", "Num"):
            val = d.get(candidate_key)
            if val is not None:
                try:
                    obj.data = float(val)
                    break
                except (ValueError, TypeError):
                    pass
        return obj

    @classmethod
    def from_xml_element(cls, elem: ET.Element) -> "VCur":
        """Construct a VCur from an xml.etree.ElementTree Element."""
        d: dict = dict(elem.attrib)
        for child in elem:
            d[child.tag] = child.text
        return cls.from_dict(d)


# ---------------------------------------------------------------------------
# s2rx.HCur  –  Horizontal (amplitude-axis) cursor
# ---------------------------------------------------------------------------

@dataclass
class HCur:
    """
    Represents a horizontal cursor stored in the XInfo block.

    Attributes
    ----------
    id : str
        Cursor identifier.
    pos : Optional[float]
        Vertical position (amplitude units).
    lab_mode : Optional[str]
        Label display mode.
    lab_pos : Optional[str]
        Label position.
    num : Optional[str]
        Cursor number / index.
    """

    id: str = ""
    pos: Optional[float] = None
    lab_mode: Optional[str] = None
    lab_pos: Optional[str] = None
    num: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "HCur":
        obj = cls()
        obj.id = str(d.get("id", d.get("@id", "")))
        obj.lab_mode = d.get("LabMode")
        obj.lab_pos = d.get("LabPos")
        obj.num = d.get("Num")
        pos_str = d.get("Pos")
        if pos_str is not None:
            try:
                obj.pos = float(pos_str)
            except (ValueError, TypeError):
                pass
        return obj

    @classmethod
    def from_xml_element(cls, elem: ET.Element) -> "HCur":
        d: dict = dict(elem.attrib)
        for child in elem:
            d[child.tag] = child.text
        return cls.from_dict(d)


# ---------------------------------------------------------------------------
# s2rx.XInfo  –  Extended view information block
# ---------------------------------------------------------------------------

@dataclass
class XInfo:
    """
    Represents the XInfo element inside a Spike2 .s2rx XML file.

    The XInfo block holds vertical cursors (VCur), active channel (ActC)
    and horizontal cursors (HCur).

    Attributes
    ----------
    vcursor : Optional[VCur]
        The first vertical cursor, if present.
    vcursors : list[VCur]
        All vertical cursors.
    act_c : Optional[str]
        Active channel id (from ActC element).
    hcursors : list[HCur]
        All horizontal cursors.
    """

    vcursor: Optional[VCur] = None
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

        # ---- vertical cursors ----------------------------------------
        vcur_raw = d.get("VCur")
        if vcur_raw is not None:
            # May be a single dict or a list of dicts.
            if isinstance(vcur_raw, list):
                obj.vcursors = [VCur.from_dict(v) for v in vcur_raw]
            else:
                obj.vcursors = [VCur.from_dict(vcur_raw)]
            obj.vcursor = obj.vcursors[0] if obj.vcursors else None

        # ---- active channel ------------------------------------------
        act_c_raw = d.get("ActC")
        if act_c_raw is not None:
            if isinstance(act_c_raw, dict):
                obj.act_c = str(act_c_raw.get("id", act_c_raw.get("@id", "")))
            else:
                obj.act_c = str(act_c_raw)

        # ---- horizontal cursors --------------------------------------
        hcur_raw = d.get("HCur")
        if hcur_raw is not None:
            if isinstance(hcur_raw, list):
                obj.hcursors = [HCur.from_dict(h) for h in hcur_raw]
            else:
                obj.hcursors = [HCur.from_dict(hcur_raw)]

        return obj

    @classmethod
    def from_xml_element(cls, elem: ET.Element) -> "XInfo":
        """Construct an XInfo by parsing an xml.etree.ElementTree Element."""
        obj = cls()

        # ---- vertical cursors ----------------------------------------
        vcur_elems = elem.findall("VCur")
        if vcur_elems:
            obj.vcursors = [VCur.from_xml_element(e) for e in vcur_elems]
            obj.vcursor = obj.vcursors[0]

        # ---- active channel ------------------------------------------
        act_c_elem = elem.find("ActC")
        if act_c_elem is not None:
            obj.act_c = act_c_elem.get("id", act_c_elem.text)

        # ---- horizontal cursors --------------------------------------
        hcur_elems = elem.findall("HCur")
        if hcur_elems:
            obj.hcursors = [HCur.from_xml_element(e) for e in hcur_elems]

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
        Return the numeric positions of all vertical cursors.

        Mirrors MATLAB::

            function t = getVerticalCursorPositions(obj)
                t = [];
                if ~isempty(obj.x_info) && ~isempty(obj.x_info.vcursor)
                    t = obj.x_info.vcursor.data;
                end
            end

        Returns
        -------
        list of float
            Cursor positions in seconds, or an empty list if none are
            found.  In the MATLAB code only ``vcursor`` (the first cursor)
            is returned; this Python version returns all cursor positions
            to be more useful, but the first element matches the MATLAB
            behaviour.
        """
        if self.x_info is None:
            return []
        if self.x_info.vcursor is None:
            return []

        # Return the data value of every vertical cursor (not just the
        # first), filtering out None.
        positions = [
            c.data for c in self.x_info.vcursors if c.data is not None
        ]
        return positions

    def get_horizontal_cursor_positions(self) -> list:
        """
        Return the numeric positions (amplitudes) of all horizontal cursors.

        Returns
        -------
        list of float
            Cursor positions, or an empty list.
        """
        if self.x_info is None:
            return []
        return [c.pos for c in self.x_info.hcursors if c.pos is not None]

    def __repr__(self) -> str:
        vcur_count = len(self.x_info.vcursors) if self.x_info else 0
        return (
            f"S2rxFile(file_path={self.file_path!r}, "
            f"vcursors={vcur_count})"
        )


