#!/usr/bin/env python3
"""
ui_shared.py — Single source of truth for colours, style sheets, and helpers.

Every UI module imports from here so that changing one colour token or style
sheet propagates everywhere without hunting through individual widget files.

Sections
--------
1.  Colour tokens         — named hex values used throughout all style sheets
2.  Style sheet constants — reusable QSS fragments applied to widget classes
3.  build_card()          — factory for the card layout used in every tab
4.  CFD helpers           — pure-Python utilities shared between tab widgets
"""

import os
import glob
import subprocess
from typing import Optional, Callable

from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QPushButton, QLineEdit,
                              QFrame)
from PyQt5.QtCore import Qt, pyqtSignal

# ── 1. Colour tokens ──────────────────────────────────────────────────────────
# Brand / structural colours
KS_RED        = "#E90029"   # primary action colour (buttons, active tab pills)
KS_RED_DARK   = "#B8001F"   # hover state for KS_RED
KS_RED_LT     = "#FEF2F4"   # light tint used for error backgrounds
KS_BLACK      = "#1A1A1A"   # header bar and status bar background
BG_APP        = "#F4F4F4"   # main content area background
BG_CARD       = "#FFFFFF"   # card / input field background
BG_SUBTLE     = "#FAFAFA"   # card header strip and disabled-field background
BORDER        = "#E5E7EB"   # standard 1 px border colour
BORDER_SOFT   = "#F3F4F6"   # very light separator lines inside cards
TEXT_PRIMARY  = "#1A1A1A"   # body text
TEXT_MUTED    = "#6B7280"   # labels, helper text, placeholder-like text
TEXT_WHITE    = "#FFFFFF"   # text on dark backgrounds

# Log drawer colours (dark terminal theme)
LOG_BG        = "#1E2329"   # terminal background
LOG_FG        = "#E2E8F0"   # default log text
LOG_ERROR     = "#FCA5A5"   # lines tagged "error"
LOG_WARN      = "#FCD34D"   # lines tagged "warn"
LOG_INFO      = "#93C5FD"   # lines tagged "info"
LOG_CMD       = "#64748B"   # lines tagged "cmd" (the command that was run)

# ── OpenFOAM constants ────────────────────────────────────────────────────────
# Full path to the OpenFOAM bashrc that must be sourced before any OF command.
# Every subprocess call prepends "source OF_BASHRC &&" because the OF environment
# is not inherited by child processes launched from the Python GUI.
OF_BASHRC      = "/usr/lib/openfoam/openfoam2506/etc/bashrc"

# Valid patch/boundary types that snappyHexMesh understands.
BOUNDARY_TYPES = ["wall", "patch", "faceZone"]

# foamDictionary uses the plural form when writing the inGroups list.
PLURAL_MAP     = {"wall": "walls", "patch": "patches", "faceZone": "faceZones"}

# ── 2. Style sheet constants ─────────────────────────────────────────────────
# These are plain strings injected via widget.setStyleSheet().  Keeping them
# here means every widget automatically picks up any visual tweak without code
# changes in the individual tab files.

STYLE_BTN_PRIMARY = f"""
    QPushButton {{
        background: {KS_RED};
        color: {TEXT_WHITE};
        border: none;
        border-radius: 4px;
        padding: 10px 20px;
        font-family: 'Segoe UI';
        font-size: 14px;
        font-weight: 600;
    }}
    QPushButton:hover    {{ background: {KS_RED_DARK}; }}
    QPushButton:disabled {{ background: {BORDER}; color: {TEXT_MUTED}; }}
"""

STYLE_BTN_GHOST = f"""
    QPushButton {{
        background: transparent;
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 9px 18px;
        font-family: 'Segoe UI';
        font-size: 14px;
    }}
    QPushButton:hover    {{ border-color: {TEXT_MUTED}; }}
    QPushButton:disabled {{ color: {TEXT_MUTED}; }}
"""

STYLE_BTN_SMALL_GHOST = f"""
    QPushButton {{
        background: transparent;
        color: {TEXT_MUTED};
        border: 1px solid {BORDER};
        border-radius: 3px;
        padding: 6px 13px;
        font-family: 'Segoe UI';
        font-size: 13px;
    }}
    QPushButton:hover {{ border-color: {TEXT_MUTED}; color: {TEXT_PRIMARY}; }}
"""

STYLE_ENTRY = f"""
    QLineEdit {{
        background: {BG_CARD};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 8px 10px;
        font-family: 'Segoe UI';
        font-size: 14px;
        min-height: 28px;
    }}
    QLineEdit:focus    {{ border-color: {KS_RED}; }}
    QLineEdit:disabled {{ background: {BG_SUBTLE}; color: {TEXT_MUTED}; }}
"""

STYLE_ENTRY_MONO = f"""
    QLineEdit {{
        background: {BG_CARD};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 7px 10px;
        font-family: Consolas;
        font-size: 12px;
    }}
    QLineEdit:focus {{ border-color: {KS_RED}; }}
"""

STYLE_SPINBOX = f"""
    QSpinBox, QDoubleSpinBox {{
        background: {BG_CARD};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 5px 24px 5px 8px;
        font-family: 'Segoe UI';
        font-size: 14px;
        min-height: 28px;
    }}
    QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {KS_RED}; }}
    QSpinBox::up-button, QDoubleSpinBox::up-button {{
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: 20px;
        height: 50%;
        border-left: 1px solid {BORDER};
        border-bottom: 1px solid {BORDER};
        border-top-right-radius: 4px;
        background: {BG_SUBTLE};
    }}
    QSpinBox::down-button, QDoubleSpinBox::down-button {{
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        width: 20px;
        height: 50%;
        border-left: 1px solid {BORDER};
        border-bottom-right-radius: 4px;
        background: {BG_SUBTLE};
    }}
    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
    QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
        background: {BORDER};
    }}
    QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
    QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {{
        background: {KS_RED}; border-color: {KS_RED};
    }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
        width: 7px; height: 7px;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-bottom: 5px solid {TEXT_MUTED};
    }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
        width: 7px; height: 7px;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {TEXT_MUTED};
    }}
"""

STYLE_CHECKBOX = f"""
    QCheckBox {{
        color: {TEXT_PRIMARY};
        font-family: 'Segoe UI';
        font-size: 14px;
        background: transparent;
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 2px solid {BORDER};
        border-radius: 3px;
        background: {BG_CARD};
    }}
    QCheckBox::indicator:checked {{
        background: {KS_RED};
        border-color: {KS_RED};
    }}
    QCheckBox::indicator:hover {{
        border-color: {TEXT_MUTED};
    }}
"""

STYLE_COMBO = f"""
    QComboBox {{
        background: {BG_CARD};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 5px 8px;
        font-family: 'Segoe UI';
        font-size: 14px;
        min-height: 28px;
    }}
    QComboBox:focus     {{ border-color: {KS_RED}; }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
        background: {BG_SUBTLE};
        border-left: 1px solid {BORDER};
        border-top-right-radius: 4px;
        border-bottom-right-radius: 4px;
    }}
    QComboBox::down-arrow {{
        width: 7px; height: 7px;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {TEXT_MUTED};
    }}
"""

STYLE_SCROLL = f"""
    QScrollBar:vertical {{
        background: {BG_APP};
        width: 8px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER};
        border-radius: 4px;
        min-height: 20px;
    }}
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollArea {{ background: {BG_APP}; border: none; }}
"""

# ── PlusMinusSpinBox ──────────────────────────────────────────────────────────

def _pm_btn_ss(border_radius: str) -> str:
    return (
        f"QPushButton {{ background: {BG_SUBTLE}; color: {TEXT_PRIMARY}; border: none;"
        f" font-family: 'Segoe UI'; font-size: 15px; font-weight: 700; padding: 0px;"
        f" border-radius: {border_radius}; }}"
        f"QPushButton:hover {{ background: {BORDER}; }}"
        f"QPushButton:pressed {{ background: {KS_RED}; color: white; }}"
        f"QPushButton:disabled {{ color: {TEXT_MUTED}; }}"
    )

_PMSP_MINUS_SS = _pm_btn_ss("3px 0px 0px 3px")
_PMSP_PLUS_SS  = _pm_btn_ss("0px 3px 3px 0px")


class PlusMinusSpinBox(QWidget):
    """
    Integer spinbox with explicit − and + buttons instead of tiny arrows.

    Drop-in replacement for QSpinBox — exposes the same interface:
      value()           → int
      setValue(int)
      setRange(int, int)
      setFixedWidth(int)   (outer widget; buttons are 22 px each, edit fills rest)
      valueChanged         signal(int)

    The centre display is an editable QLineEdit so the user can type a value
    directly in addition to clicking the buttons.
    """
    valueChanged = pyqtSignal(int)
    _BTN_W = 22

    def __init__(self, parent=None):
        super().__init__(parent)
        self._min = 0
        self._max = 99
        self._val = 0

        self.setObjectName("pmsp")
        self.setFixedHeight(32)
        self.setStyleSheet(f"""
            QWidget#pmsp {{
                background: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 4px;
            }}
        """)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        self._minus = QPushButton("−")
        self._minus.setFixedWidth(self._BTN_W)
        self._minus.setStyleSheet(_PMSP_MINUS_SS)
        self._minus.clicked.connect(lambda: self._step(-1))

        sep_l = QFrame()
        sep_l.setFixedWidth(1)
        sep_l.setStyleSheet(f"QFrame {{ background: {BORDER}; }}")

        self._edit = QLineEdit("0")
        self._edit.setAlignment(Qt.AlignCenter)
        self._edit.setStyleSheet(
            f"QLineEdit {{ color: {TEXT_PRIMARY}; font-family: 'Segoe UI';"
            f" font-size: 13px; background: {BG_CARD}; border: none; padding: 0px; }}"
        )
        self._edit.editingFinished.connect(self._on_edit_done)

        sep_r = QFrame()
        sep_r.setFixedWidth(1)
        sep_r.setStyleSheet(f"QFrame {{ background: {BORDER}; }}")

        self._plus = QPushButton("+")
        self._plus.setFixedWidth(self._BTN_W)
        self._plus.setStyleSheet(_PMSP_PLUS_SS)
        self._plus.clicked.connect(lambda: self._step(1))

        row.addWidget(self._minus)
        row.addWidget(sep_l)
        row.addWidget(self._edit, 1)
        row.addWidget(sep_r)
        row.addWidget(self._plus)

    def _step(self, delta: int):
        nv = max(self._min, min(self._max, self._val + delta))
        if nv != self._val:
            self._val = nv
            self._edit.setText(str(nv))
            self.valueChanged.emit(nv)

    def _on_edit_done(self):
        try:
            nv = max(self._min, min(self._max, int(self._edit.text())))
        except ValueError:
            nv = self._val
        self._edit.setText(str(nv))
        if nv != self._val:
            self._val = nv
            self.valueChanged.emit(nv)

    def value(self) -> int:
        return self._val

    def setValue(self, v: int):
        self._val = max(self._min, min(self._max, int(v)))
        self._edit.setText(str(self._val))

    def setRange(self, lo: int, hi: int):
        self._min, self._max = lo, hi
        self._val = max(lo, min(hi, self._val))
        self._edit.setText(str(self._val))


# ── 3. Card builder ───────────────────────────────────────────────────────────

def build_card(section_label: str, title: str):
    """
    Build the standard two-part card used throughout both tabs.

    Layout (top to bottom inside the returned QFrame):
      ┌─────────────────────────────────────────────┐
      │  [section_label]  [title]        (header)   │  44 px, BG_SUBTLE
      ├─────────────────────────────────────────────┤  1 px BORDER_SOFT separator
      │  body area (caller populates via body_vbox) │  BG_CARD, 18/14/18/18 margins
      └─────────────────────────────────────────────┘

    Returns
    -------
    card      : QFrame  — the outer container; add to a parent layout
    body_vbox : QVBoxLayout — the inner layout; add child widgets here
    """
    from PyQt5.QtWidgets import (QFrame, QWidget, QVBoxLayout, QHBoxLayout,
                                  QLabel)
    from PyQt5.QtCore import Qt

    card = QFrame()
    card.setObjectName("card")
    card.setStyleSheet(f"""
        QFrame#card {{
            background: {BG_CARD};
            border: 1px solid {BORDER};
            border-radius: 6px;
        }}
    """)

    vbox = QVBoxLayout(card)
    vbox.setContentsMargins(0, 0, 0, 0)
    vbox.setSpacing(0)

    hdr = QWidget()
    hdr.setObjectName("card_hdr")
    hdr.setFixedHeight(44)
    hdr.setStyleSheet(f"""
        QWidget#card_hdr {{
            background: {BG_SUBTLE};
            border-radius: 5px 5px 0 0;
        }}
    """)

    hdr_row = QHBoxLayout(hdr)
    hdr_row.setContentsMargins(18, 0, 18, 0)
    hdr_row.setSpacing(10)

    num_lbl = QLabel(section_label)
    num_lbl.setStyleSheet(
        f"color: {KS_RED}; font-family: Consolas; font-size: 12px;"
        " font-weight: bold; background: transparent;"
    )

    ttl_lbl = QLabel(title)
    ttl_lbl.setStyleSheet(
        f"color: {TEXT_PRIMARY}; font-family: 'Segoe UI'; font-size: 15px;"
        " font-weight: 600; background: transparent;"
    )

    hdr_row.addWidget(num_lbl)
    hdr_row.addWidget(ttl_lbl)
    hdr_row.addStretch()
    vbox.addWidget(hdr)

    sep = QFrame()
    sep.setFixedHeight(1)
    sep.setStyleSheet(f"QFrame {{ background: {BORDER_SOFT}; }}")
    vbox.addWidget(sep)

    body_w = QWidget()
    body_w.setObjectName("card_body")
    body_w.setStyleSheet(f"QWidget#card_body {{ background: {BG_CARD}; border-radius: 0 0 5px 5px; }}")
    body_vbox = QVBoxLayout(body_w)
    body_vbox.setContentsMargins(18, 14, 18, 18)
    body_vbox.setSpacing(10)
    vbox.addWidget(body_w)

    return card, body_vbox


# ── 4. CFD helpers ────────────────────────────────────────────────────────────

def positive_float(value) -> Optional[float]:
    """
    Return float(value) if strictly positive, else None.

    Used to validate DX/DY/DZ grid size inputs.  Unlike the CLI version in
    generateBackgroundMesh.py (which raises argparse.ArgumentTypeError), this
    returns None so that the GUI can show an inline error label instead of
    crashing.
    """
    try:
        v = float(value)
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def get_stl_zone_names(path: str) -> list:
    """
    Parse an ASCII STL file and return the list of solid/zone names.

    Each 'solid <name>' line in the STL defines one zone.  A file with a single
    unnamed solid returns ["Unnamed"].  The list drives the per-zone surface
    refinement rows in the snappyHexMesh Dict tab.
    """
    try:
        with open(path, "r", errors="ignore") as fh:
            lines = fh.readlines()
        names = []
        for line in lines:
            s = line.strip()
            if s.lower().startswith("solid"):
                parts = s.split(maxsplit=1)
                names.append(parts[1] if len(parts) > 1 else "Unnamed")
        return names
    except Exception:
        return []


def find_paraview_exe() -> Optional[str]:
    """
    Find the newest installed ParaView executable visible from WSL.

    ParaView is installed on the Windows side (C:\\Program Files\\ParaView*).
    From WSL that path appears under /mnt/c/.  We glob for all versions and
    return the lexicographically last one, which corresponds to the highest
    version number because the directory names are versioned (e.g. ParaView-5.12).
    """
    matches = sorted(glob.glob("/mnt/c/Program Files/ParaView*/bin/paraview.exe"))
    return matches[-1] if matches else None


def run_of_command(cmd: str, cwd: str, log_callback: Callable) -> int:
    """
    Run an OpenFOAM command in WSL, streaming output to the log in real time.

    The command is wrapped in a bash -c call that first sources the OpenFOAM
    bashrc so that tools like blockMesh and snappyHexMesh are on PATH.

    stderr is merged into stdout (stderr=STDOUT) so error messages appear in
    the correct position in the log rather than at the end.  The log_callback
    receives each line as it arrives, which gives the user live feedback for
    long-running commands like blockMesh and snappyHexMesh.

    Parameters
    ----------
    cmd          : shell command string (no need to source OF yourself)
    cwd          : working directory — must be the OpenFOAM case root
    log_callback : callable(line: str, tag: str) that writes to the LogDrawer

    Returns
    -------
    exit code (0 = success)
    """
    log_callback(f"  $ {cmd}\n", "cmd")
    bash_cmd = f"source {OF_BASHRC} && {cmd}"
    try:
        proc = subprocess.Popen(
            ["bash", "-c", bash_cmd],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=cwd,
        )
        for line in proc.stdout:
            tag = "error" if any(w in line.lower() for w in ("error", "fail")) else ""
            log_callback(line, tag)
        proc.wait()
        return proc.returncode
    except Exception as exc:
        log_callback(f"  Exception: {exc}\n", "error")
        return -1


def run_foam_cmd(cmd: str, cwd: str, log_callback: Callable) -> int:
    """
    Run a quick foamDictionary command, blocking until it finishes.

    Unlike run_of_command (which streams line-by-line), this captures all
    output at once using capture_output=True.  foamDictionary prints verbose
    diagnostic lines to stderr even on success, so we suppress stderr unless
    the exit code is non-zero.  This keeps the log clean during the many
    sequential foamDictionary calls that build snappyHexMeshDict.

    Use this helper for short-lived dictionary-manipulation commands.
    Use run_of_command for long-running solver calls (blockMesh, snappyHexMesh).
    """
    log_callback(f"  $ {cmd}\n", "cmd")
    bash_cmd = f"source {OF_BASHRC} && {cmd}"
    try:
        r = subprocess.run(["bash", "-c", bash_cmd], text=True,
                           capture_output=True, cwd=cwd)
        if r.stdout:
            log_callback(r.stdout)
        if r.returncode != 0 and r.stderr:
            log_callback(r.stderr, "error")
        return r.returncode
    except Exception as exc:
        log_callback(f"  Exception: {exc}\n", "error")
        return -1
