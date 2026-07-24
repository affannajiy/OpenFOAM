#!/usr/bin/env python3
"""
ui_shared.py — Single source of truth for colours, style sheets, and helpers.

Every UI module imports from here so that changing one colour token or style
sheet propagates everywhere without hunting through individual widget files.

Sections
--------
1.  Colour tokens         — named hex values used throughout all style sheets
2.  Style sheet constants — reusable QSS fragments applied to widget classes
    (plus ChevronComboBox and PlusMinusSpinBox — custom input widgets)
3.  build_card()          — factory for the card layout used in every tab
4.  CFD helpers           — pure-Python utilities shared between tab widgets
5.  Plain-language error map — OF_ERROR_MAP + scan_log_for_fix()
6.  MessageBanner         — green/red result strip shown above the log
"""

import os
import glob
import json
import subprocess
from typing import Optional, Callable

from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
                              QLineEdit, QFrame, QComboBox, QLabel, QSizePolicy,
                              QMessageBox, QApplication, QFileDialog,
                              QFileIconProvider, QToolButton)
from PyQt5.QtCore import (Qt, pyqtSignal, QEvent, QTimer, QObject, QEventLoop,
                          QFileInfo, QDir)
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QIcon

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
BORDER_STRONG = "#9CA3AF"   # darker 1 px border — visible group outline on white
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

# ── 1b. Font tokens ───────────────────────────────────────────────────────────
# The GUI renders under WSL, so Windows font names never resolve: fontconfig
# silently substituted DejaVu for both 'Segoe UI' and Consolas.  Single family
# names are used deliberately — fontconfig always resolves them to *something*,
# whereas Qt5's QSS parser is unreliable with comma-separated fallback lists.
#
# FONT_UI resolves to Nimbus Sans (metrically Helvetica-compatible) when the
# fonts-urw-base35 package is present — the launcher's apt setup installs it —
# and degrades to DejaVu Sans when it is not.
#
# FONT_MONO stays a separate role on purpose: the log drawer and the coordinate
# / path / value fields rely on fixed-width columns to stay aligned with raw
# snappyHexMesh output.  Never collapse it into FONT_UI.
FONT_UI       = "Helvetica"
FONT_MONO     = "monospace"

# ── OpenFOAM constants ────────────────────────────────────────────────────────
# Full path to the OpenFOAM bashrc that must be sourced before any OF command.
# Every subprocess call prepends "source OF_BASHRC &&" because the OF environment
# is not inherited by child processes launched from the Python GUI.
# Resolved once at import: the install the GUI was launched under
# ($WM_PROJECT_DIR, set because the launcher sources the bashrc), else the
# newest /usr/lib/openfoam install, else the 2506 default path.

def _detect_of_bashrc() -> str:
    """Locate the OpenFOAM bashrc: launch env → newest install → 2506 default."""
    proj = os.environ.get("WM_PROJECT_DIR", "").strip()
    if proj:
        cand = os.path.join(proj, "etc", "bashrc")
        if os.path.isfile(cand):
            return cand
    installs = sorted(glob.glob("/usr/lib/openfoam/openfoam[0-9]*/etc/bashrc"))
    if installs:
        return installs[-1]
    return "/usr/lib/openfoam/openfoam2506/etc/bashrc"


OF_BASHRC      = _detect_of_bashrc()

# Valid patch/boundary types that snappyHexMesh understands.
BOUNDARY_TYPES = ["wall", "patch", "faceZone"]

# foamDictionary uses the plural form when writing the inGroups list.
PLURAL_MAP     = {"wall": "walls", "patch": "patches", "faceZone": "faceZones"}

# ── 2. Style sheet constants ─────────────────────────────────────────────────
# These are plain strings injected via widget.setStyleSheet().  Keeping them
# here means every widget automatically picks up any visual tweak without code
# changes in the individual tab files.

# Applied once, app-wide, via QApplication.setStyleSheet() so every tooltip in
# the GUI (Sections 01-05, headers, buttons) shares one look instead of each
# platform's default OS tooltip.
STYLE_TOOLTIP = f"""
    QToolTip {{
        background: {BG_CARD};
        color: {TEXT_PRIMARY};
        border: 2px solid {KS_RED};
        border-radius: 6px;
        padding: 6px 8px;
        font-size: 12px;
        font-family: {FONT_MONO};
    }}
"""

STYLE_BTN_PRIMARY = f"""
    QPushButton {{
        background: {KS_RED};
        color: {TEXT_WHITE};
        border: none;
        border-radius: 4px;
        padding: 10px 20px;
        font-family: {FONT_UI};
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
        font-family: {FONT_UI};
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
        font-family: {FONT_UI};
        font-size: 13px;
    }}
    QPushButton:hover {{ border-color: {TEXT_MUTED}; color: {TEXT_PRIMARY}; }}
"""

STYLE_BTN_SMALL_RED = f"""
    QPushButton {{
        background: {KS_RED};
        color: {TEXT_WHITE};
        border: none;
        border-radius: 3px;
        padding: 6px 13px;
        font-family: {FONT_UI};
        font-size: 13px;
        font-weight: 600;
    }}
    QPushButton:hover    {{ background: {KS_RED_DARK}; }}
    QPushButton:disabled {{ background: {BORDER}; color: {TEXT_MUTED}; }}
"""

STYLE_ENTRY = f"""
    QLineEdit {{
        background: {BG_CARD};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 8px 10px;
        font-family: {FONT_UI};
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
        font-family: {FONT_MONO};
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
        font-family: {FONT_UI};
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

# White ✓ glyph for the checked indicator — QSS cannot draw glyphs itself, so
# a pre-rendered PNG ships in icons/ (see deploy notes). Forward slashes: Qt
# url() requires them even on Windows, and the app runs under WSL anyway.
_CHECK_PNG = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "icons", "check_16.png"
).replace("\\", "/")

STYLE_CHECKBOX = f"""
    QCheckBox {{
        color: {TEXT_PRIMARY};
        font-family: {FONT_UI};
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
        image: url({_CHECK_PNG});
    }}
    QCheckBox::indicator:checked:disabled {{
        background: {BORDER};
        border-color: {BORDER};
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
        font-family: {FONT_UI};
        font-size: 14px;
        min-height: 28px;
    }}
    QComboBox:focus     {{ border-color: {KS_RED}; }}
    QComboBox:disabled  {{
        background: {BG_SUBTLE};
        color: {TEXT_MUTED};
        border-color: {BORDER};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
        background: {BG_SUBTLE};
        border-left: 1px solid {BORDER};
        border-top-right-radius: 4px;
        border-bottom-right-radius: 4px;
    }}
    QComboBox::down-arrow {{
        image: none;
        width: 0px;
        height: 0px;
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

# Qt merges an owner widget's own stylesheet into the tooltip shown over it, so
# a widget rule like `color: KS_RED` (header labels) or `color: TEXT_PRIMARY`
# (combos) leaks into its tooltip and beats the app-wide QToolTip rule — the
# tooltip came out red-on-dark instead of black-on-white.  Appending the
# QToolTip block to every widget-level stylesheet forces the white bg / black
# text / red rounded border everywhere the tooltip is actually rendered.
for _n in ("STYLE_BTN_PRIMARY", "STYLE_BTN_GHOST", "STYLE_BTN_SMALL_GHOST",
           "STYLE_BTN_SMALL_RED", "STYLE_ENTRY", "STYLE_ENTRY_MONO",
           "STYLE_SPINBOX", "STYLE_CHECKBOX", "STYLE_COMBO", "STYLE_SCROLL"):
    globals()[_n] += STYLE_TOOLTIP

# ── ChevronComboBox ───────────────────────────────────────────────────────────

# Width of the drop-down box drawn by STYLE_COMBO's ::drop-down rule — the
# chevron label is sized to sit centred inside that box.
_COMBO_DROPDOWN_W = 24


class ChevronComboBox(QComboBox):
    """
    QComboBox with a real text arrow ('▼') drawn as a child QLabel, the same
    approach the log drawer's collapse button uses (self._chevron_btn.setText
    ("▼")) — instead of the QSS border-triangle trick, which is fragile and
    rendered as a solid block rather than a triangle. Drop-in replacement for
    QComboBox; still pair with STYLE_COMBO (which hides the native arrow).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._chevron = QLabel("▼", self)
        self._chevron.setStyleSheet(
            f"QLabel {{ color: {KS_RED}; font-size: 9px; background: transparent; }}")
        self._chevron.setAlignment(Qt.AlignCenter)
        self._chevron.setAttribute(Qt.WA_TransparentForMouseEvents)

    def resizeEvent(self, event):
        # Keep the ▼ label parked over the drop-down box (right edge) whenever
        # the combo changes size — QLabel children don't follow layouts here.
        super().resizeEvent(event)
        self._chevron.setGeometry(
            self.width() - _COMBO_DROPDOWN_W, 0, _COMBO_DROPDOWN_W, self.height())

    def changeEvent(self, event):
        # Grey the ▼ arrow to match the muted text/background when the combo is
        # disabled — the QLabel child isn't covered by QComboBox:disabled QSS.
        super().changeEvent(event)
        if event.type() == QEvent.EnabledChange:
            col = KS_RED if self.isEnabled() else TEXT_MUTED
            self._chevron.setStyleSheet(
                f"QLabel {{ color: {col}; font-size: 9px; background: transparent; }}")


# ── PlusMinusSpinBox ──────────────────────────────────────────────────────────

def _pm_btn_ss(border_radius: str) -> str:
    """Return the QSS for a PlusMinusSpinBox − or + button with the given border-radius."""
    return (
        f"QPushButton {{ background: {BG_SUBTLE}; color: {TEXT_PRIMARY}; border: none;"
        f" font-family: {FONT_UI}; font-size: 15px; font-weight: 700; padding: 0px;"
        f" border-radius: {border_radius}; }}"
        f"QPushButton:hover {{ background: {BORDER}; }}"
        f"QPushButton:pressed {{ background: {KS_RED}; color: white; }}"
        f"QPushButton:disabled {{ color: {TEXT_MUTED}; }}"
        + STYLE_TOOLTIP
    )

_PMSP_MINUS_SS = _pm_btn_ss("3px 0px 0px 3px")
_PMSP_PLUS_SS  = _pm_btn_ss("0px 3px 3px 0px")


class PlusMinusSpinBox(QWidget):
    """
    Number picker with explicit − (left) and + (right) buttons instead of
    tiny up/down arrows — the side-by-side layout the user asked for so it's
    obvious at a glance that clicking − / + changes the value.

    Drop-in replacement for QSpinBox/QDoubleSpinBox — exposes the same interface:
      value()           → int (decimals=0) or float (decimals>0)
      setValue(number)
      setRange(lo, hi)
      setPrefix(str)       (e.g. "x: ", shown before the number, non-editable)
      setFixedWidth(int)   (outer widget; buttons are 22 px each, edit fills rest)
      valueChanged         signal(float)

    Pass decimals > 0 for a float picker (e.g. mesh coordinates); step defaults
    to 1 per click either way. The centre display is an editable QLineEdit so
    the user can type a value directly in addition to clicking the buttons.
    """
    valueChanged = pyqtSignal(float)
    _BTN_W = 22

    def __init__(self, parent=None, decimals: int = 0, step: float = 1):
        super().__init__(parent)
        self._min = 0
        self._max = 99
        self._val = 0.0
        self._decimals = decimals
        self._step = step
        self._prefix = ""

        self.setObjectName("pmsp")
        # QWidget subclasses ignore stylesheet border/background unless this is
        # set — without it the #pmsp group outline never paints (Qt5 quirk).
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(32)
        self.setStyleSheet(f"""
            QWidget#pmsp {{
                background: {BG_CARD};
                border: 1px solid {BORDER_STRONG};
                border-radius: 4px;
            }}
            QWidget#pmsp:disabled {{
                background: {BG_SUBTLE};
                border: 1px solid {BORDER};
            }}
        """ + STYLE_TOOLTIP)

        row = QHBoxLayout(self)
        # 1 px inset so the −/+ buttons sit INSIDE the outer border instead of
        # painting over it — kills the white-sliver notch at the rounded corners
        # (button inner radius 3 px = outer 4 px − 1 px border).
        row.setContentsMargins(1, 1, 1, 1)
        row.setSpacing(0)

        self._minus = QPushButton("−")
        self._minus.setFixedWidth(self._BTN_W)
        self._minus.setStyleSheet(_PMSP_MINUS_SS)
        self._minus.setCursor(Qt.PointingHandCursor)
        self._minus.setToolTip("Decrease")
        self._minus.clicked.connect(lambda: self._step_by(-1))

        sep_l = QFrame()
        sep_l.setFixedWidth(1)
        sep_l.setStyleSheet(f"QFrame {{ background: {BORDER_STRONG}; }}")

        self._edit = QLineEdit(self._fmt(0))
        self._edit.setAlignment(Qt.AlignCenter)
        self._edit.setStyleSheet(
            f"QLineEdit {{ color: {TEXT_PRIMARY}; font-family: {FONT_UI};"
            f" font-size: 13px; background: {BG_CARD}; border: none; padding: 0px; }}"
            f"QLineEdit:disabled {{ color: {TEXT_MUTED}; background: {BG_SUBTLE}; }}"
            + STYLE_TOOLTIP
        )
        self._edit.editingFinished.connect(self._on_edit_done)

        sep_r = QFrame()
        sep_r.setFixedWidth(1)
        sep_r.setStyleSheet(f"QFrame {{ background: {BORDER_STRONG}; }}")

        self._plus = QPushButton("+")
        self._plus.setFixedWidth(self._BTN_W)
        self._plus.setStyleSheet(_PMSP_PLUS_SS)
        self._plus.setCursor(Qt.PointingHandCursor)
        self._plus.setToolTip("Increase")
        self._plus.clicked.connect(lambda: self._step_by(1))

        row.addWidget(self._minus)
        row.addWidget(sep_l)
        row.addWidget(self._edit, 1)
        row.addWidget(sep_r)
        row.addWidget(self._plus)

    def _fmt(self, v) -> str:
        """Format a number for the display box: round it, add the prefix
        (e.g. "x: "), and show the configured number of decimals."""
        v = round(v, self._decimals) if self._decimals else int(round(v))
        return f"{self._prefix}{v:.{self._decimals}f}" if self._decimals else f"{self._prefix}{v}"

    def _step_by(self, direction: int):
        """Handle a − or + click: move the value one step (direction is -1 or
        +1), clamp to the min/max range, and emit valueChanged if it moved."""
        nv = max(self._min, min(self._max, self._val + direction * self._step))
        if nv != self._val:
            self._val = nv
            self._edit.setText(self._fmt(nv))
            self.valueChanged.emit(nv)

    def _on_edit_done(self):
        """Handle the user typing a value directly: strip the prefix, parse the
        number, clamp to range. Bad input (letters etc.) reverts to the previous
        value instead of erroring."""
        text = self._edit.text().strip()
        if self._prefix and text.startswith(self._prefix):
            text = text[len(self._prefix):]
        try:
            nv = max(self._min, min(self._max, float(text)))
        except ValueError:
            nv = self._val  # not a number — keep the old value
        self._edit.setText(self._fmt(nv))
        if nv != self._val:
            self._val = nv
            self.valueChanged.emit(nv)

    # -- public QSpinBox-compatible interface --------------------------------

    def value(self):
        """Current value — int when decimals=0, float otherwise."""
        return round(self._val, self._decimals) if self._decimals else int(round(self._val))

    def setValue(self, v):
        """Set the value programmatically (clamped to range, no signal)."""
        self._val = max(self._min, min(self._max, float(v)))
        self._edit.setText(self._fmt(self._val))

    def setRange(self, lo, hi):
        """Set min/max limits; the current value is clamped into the new range."""
        self._min, self._max = lo, hi
        self._val = max(lo, min(hi, self._val))
        self._edit.setText(self._fmt(self._val))

    def setPrefix(self, prefix: str):
        """Set a text label shown before the number, e.g. "x: "."""
        self._prefix = prefix
        self._edit.setText(self._fmt(self._val))


# ── 3. Card builder ───────────────────────────────────────────────────────────

def make_info_icon(tip_text: str, bg: str = None):
    """
    Small clickable-looking 'ⓘ' help badge that carries a tooltip.

    Give the user one obvious spot to hover instead of hunting over a whole
    label or header.  The badge sets a SOLID background (never transparent):
    Qt leaks an owner widget's own background into its tooltip, and a
    transparent owner makes the tooltip render see-through — the exact bug
    this replaces.  STYLE_TOOLTIP is appended so the badge keeps the shared
    white-bg / black-text / red-border look.

    Parameters
    ----------
    tip_text : str   — help text shown on hover.
    bg       : str   — solid background behind the badge; match the strip it
                       sits on so it blends in.  Defaults to BG_CARD.
    """
    from PyQt5.QtWidgets import QLabel
    from PyQt5.QtCore import Qt

    if bg is None:
        bg = BG_CARD
    # Circle drawn with QSS (border + border-radius), NOT a Unicode glyph.
    # The old 'ⓘ' (U+24D8) is missing from the default Qt/Linux font and
    # rendered as a tofu box.  An ASCII 'i' always renders.
    icon = QLabel("i")
    icon.setStyleSheet(
        f"QLabel {{ color: {KS_RED}; font-family: {FONT_UI}; font-size: 11px;"
        f" font-weight: 700; font-style: italic; background: {bg};"
        f" border: 1.4px solid {KS_RED}; border-radius: 8px; }}"
        + STYLE_TOOLTIP)
    icon.setFixedSize(16, 16)
    icon.setAlignment(Qt.AlignCenter)
    icon.setCursor(Qt.WhatsThisCursor)
    icon.setToolTip(tip_text)
    return icon


def build_card(section_label: str, title: str, tip: str = None):
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
        f"color: {KS_RED}; font-family: {FONT_MONO}; font-size: 12px;"
        " font-weight: bold; background: transparent;"
    )

    ttl_lbl = QLabel(title)
    ttl_lbl.setStyleSheet(
        f"color: {TEXT_PRIMARY}; font-family: {FONT_UI}; font-size: 15px;"
        " font-weight: 600; background: transparent;"
    )

    hdr_row.addWidget(num_lbl)
    hdr_row.addWidget(ttl_lbl)
    if tip:
        hdr_row.addWidget(make_info_icon(tip, bg=BG_SUBTLE))
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


# ── 3b. User preferences ──────────────────────────────────────────────────────
#
# Small per-user JSON file remembering last-used numeric settings across app
# restarts (grid sizes, unit, nCellsBetweenLevels, layers toggle).  Deliberately
# NOT per-project: case-specific values (locationInMesh, file-table rows) are
# excluded because they would be wrong when carried to a different geometry.

_PREFS_PATH = os.path.expanduser("~/.openfoam_ui_prefs.json")


def load_prefs() -> dict:
    """Return the saved preferences dict, or {} if missing/corrupt."""
    try:
        with open(_PREFS_PATH) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_prefs(updates: dict):
    """Merge *updates* into the prefs file (existing keys not in updates survive).
    Best-effort — a read-only home dir must never break a mesh run."""
    try:
        prefs = load_prefs()
        prefs.update(updates)
        with open(_PREFS_PATH, "w") as f:
            json.dump(prefs, f, indent=2)
    except Exception:
        pass


# ── 3c. In-window popups (message boxes + file pickers) ──────────────────────
#
# Weston (WSLg's window manager) forcibly re-places every managed top-level
# window at a screen corner one frame after it maps — even when positioned
# before show() — so any real dialog flashes at the corner first.  Bypassing
# the window manager (X11BypassWindowManagerHint) avoids the flash but breaks
# input focus, which made boxes unclickable and locked the whole app.
#
# The robust fix is to never create a top-level dialog at all: popups are
# rendered as an in-window OVERLAY — a child widget of the main window with a
# dimmed backdrop and a centred card.  Weston never sees a child widget, so
# the popup appears instantly at the centre, gets input like any other
# widget, and cannot be mis-placed, lose focus, or get stuck.

class _PopupOverlay(QWidget):
    """Dimmed full-window backdrop that centres a content card and runs a
    local event loop until the card resolves. Child of the main window —
    never a top-level window, so WSLg/Weston cannot interfere with it."""

    def __init__(self, host_window):
        super().__init__(host_window)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: rgba(0, 0, 0, 96);" + STYLE_TOOLTIP)
        self.setGeometry(host_window.rect())
        host_window.installEventFilter(self)   # track window resizes
        self._loop = QEventLoop(self)
        self.result = None

    def eventFilter(self, obj, event):
        if obj is self.parent() and event.type() == QEvent.Resize:
            self.setGeometry(self.parent().rect())
            self._recenter_card()
        return False

    def resizeEvent(self, event):
        self._recenter_card()
        super().resizeEvent(event)

    def _recenter_card(self):
        for child in self.children():
            if isinstance(child, QWidget) and child.isVisible():
                g = child.geometry()
                g.moveCenter(self.rect().center())
                child.setGeometry(g)

    def mousePressEvent(self, event):
        event.accept()   # swallow clicks on the backdrop → modal behaviour

    def finish(self, result):
        self.result = result
        self._loop.quit()

    def run(self, card):
        """Show overlay + centred *card*, block in a local event loop until
        finish() is called, then tear everything down. Returns .result."""
        card.adjustSize()
        g = card.geometry()
        g.moveCenter(self.rect().center())
        card.setGeometry(g)
        self.show()
        self.raise_()
        card.show()
        card.setFocus()
        try:
            self._loop.exec_()
        finally:
            try:
                self.parent().removeEventFilter(self)
            except Exception:
                pass
            self.hide()
            self.deleteLater()
        return self.result


def _host_window(parent):
    """Top-level widget to attach the overlay to. Falls back to the active
    window so popups still work when a worker has no widget parent."""
    if parent is not None and parent.window() is not None:
        return parent.window()
    return QApplication.activeWindow()


class _MessageCard(QFrame):
    """The white centred card of a message popup: icon + title + text +
    buttons. Esc presses the escape button; Enter presses the default."""

    _ICONS = {
        QMessageBox.Information: ("i",  "#2563EB"),
        QMessageBox.Warning:     ("!",  "#D97706"),
        QMessageBox.Critical:    ("✕", KS_RED),
        QMessageBox.Question:    ("?",  "#2563EB"),
    }

    def __init__(self, overlay, icon, title, text, buttons, default):
        super().__init__(overlay)
        self._overlay = overlay
        self.setObjectName("popupCard")
        self.setStyleSheet(f"""
            QFrame#popupCard {{
                background: {BG_CARD};
                border: 1px solid {BORDER_STRONG};
                border-radius: 8px;
            }}
            QLabel {{ background: transparent; border: none; }}
        """ + STYLE_TOOLTIP)
        self.setMinimumWidth(360)
        self.setMaximumWidth(560)

        glyph, colour = self._ICONS.get(icon, ("i", "#2563EB"))
        icon_lbl = QLabel(glyph, self)
        icon_lbl.setFixedSize(34, 34)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet(
            f"background: {colour}; color: {TEXT_WHITE}; border-radius: 17px;"
            f"font-size: 16px; font-weight: bold;")

        title_lbl = QLabel(title, self)
        title_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: bold;")
        title_lbl.setWordWrap(True)

        text_lbl = QLabel(text, self)
        text_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px;")
        text_lbl.setWordWrap(True)
        text_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)

        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(icon_lbl, 0, Qt.AlignTop)
        body = QVBoxLayout()
        body.setSpacing(6)
        body.addWidget(title_lbl)
        body.addWidget(text_lbl)
        head.addLayout(body, 1)

        self._default_btn = None
        self._escape_btn = None
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch(1)
        # Standard order: affirmative first, escape last.
        for role in (QMessageBox.Yes, QMessageBox.Ok,
                     QMessageBox.No, QMessageBox.Cancel):
            if not (buttons & role):
                continue
            label = {QMessageBox.Yes: "Yes", QMessageBox.Ok: "OK",
                     QMessageBox.No: "No", QMessageBox.Cancel: "Cancel"}[role]
            primary = role in (QMessageBox.Yes, QMessageBox.Ok)
            btn = QPushButton(label, self)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumWidth(84)
            if primary:
                btn.setStyleSheet(f"""
                    QPushButton {{ background: {KS_RED}; color: {TEXT_WHITE};
                        border: none; border-radius: 4px; padding: 7px 18px;
                        font-size: 12px; font-weight: bold; }}
                    QPushButton:hover {{ background: {KS_RED_DARK}; }}
                """ + STYLE_TOOLTIP)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{ background: {BG_CARD}; color: {TEXT_PRIMARY};
                        border: 1px solid {BORDER_STRONG}; border-radius: 4px;
                        padding: 7px 18px; font-size: 12px; }}
                    QPushButton:hover {{ background: {BG_SUBTLE}; }}
                """ + STYLE_TOOLTIP)
            btn.clicked.connect(lambda _=False, r=role: overlay.finish(r))
            btn_row.addWidget(btn)
            if role in (QMessageBox.No, QMessageBox.Cancel):
                self._escape_btn = role
            if default == role or (default == QMessageBox.NoButton
                                   and self._default_btn is None and primary):
                self._default_btn = role
                btn.setFocus()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(14)
        lay.addLayout(head)
        lay.addLayout(btn_row)
        self.setFocusPolicy(Qt.StrongFocus)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._overlay.finish(self._escape_btn if self._escape_btn
                                 else self._default_btn)
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._overlay.finish(self._default_btn)
        else:
            super().keyPressEvent(event)


def _run_box_standalone(icon, title, text, buttons, default):
    """Popup with no visible host window (e.g. the single-instance notice
    fired before the main window exists). A small top-level dialog cannot be
    used — Weston shoves it to a screen corner — but it does respect
    fullscreen windows, so the card is hosted in a temporary frameless
    fullscreen backdrop and rendered by the same overlay/card widgets as
    every in-window popup."""
    host = QWidget(None, Qt.FramelessWindowHint)
    host.setAttribute(Qt.WA_TranslucentBackground, True)
    host.showFullScreen()
    try:
        overlay = _PopupOverlay(host)
        card = _MessageCard(overlay, icon, title, text, buttons, default)
        result = overlay.run(card)
    finally:
        host.close()
        host.deleteLater()
    return result if result is not None else QMessageBox.Cancel


def _run_box(parent, icon, title, text,
             buttons=QMessageBox.Ok, default=QMessageBox.NoButton):
    """Show an in-window message popup; returns the clicked button role.
    When no host window exists yet, _run_box_standalone hosts the same card
    in a temporary fullscreen backdrop instead."""
    host = _host_window(parent)
    if host is None or not host.isVisible():
        return _run_box_standalone(icon, title, text, buttons, default)
    overlay = _PopupOverlay(host)
    card = _MessageCard(overlay, icon, title, text, buttons, default)
    result = overlay.run(card)
    return result if result is not None else QMessageBox.Cancel


def msg_info(parent, title, text):
    """Info popup (in-window overlay — see _PopupOverlay)."""
    _run_box(parent, QMessageBox.Information, title, text)


def msg_warning(parent, title, text):
    """Warning popup (in-window overlay — see _PopupOverlay)."""
    _run_box(parent, QMessageBox.Warning, title, text)


def msg_critical(parent, title, text):
    """Error popup (in-window overlay — see _PopupOverlay)."""
    _run_box(parent, QMessageBox.Critical, title, text)


def msg_question(parent, title, text, default_no=False) -> bool:
    """Yes/No question; returns True when the user picks Yes."""
    default = QMessageBox.No if default_no else QMessageBox.NoButton
    return _run_box(parent, QMessageBox.Question, title, text,
                    QMessageBox.Yes | QMessageBox.No, default) == QMessageBox.Yes


# File pickers use the same overlay: a non-native QFileDialog re-parented as
# a plain child widget (Qt.Widget flag) inside the overlay, so it too can
# never be mis-placed by Weston. Its own accepted/rejected signals resolve
# the overlay's event loop. The stock chrome (sidebar, Look-in row, Files-of-
# type row, icon toolbar) is hidden and replaced by a card-style header with
# an editable path field + Up / New Folder text buttons, so the picker matches
# the _MessageCard design.

class _FlatIconProvider(QFileIconProvider):
    """Minimal flat icons: grey folder, outline file, red-tinted mesh files."""

    _MESH_EXT = {"stl", "obj"}

    def __init__(self):
        super().__init__()
        self._cache = {}

    def _flat(self, kind):
        """Draw (and cache) a flat 24px glyph: folder, file, or red mesh file."""
        if kind in self._cache:
            return self._cache[kind]
        pm = QPixmap(24, 24)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        if kind == "folder":
            p.setPen(QPen(QColor(BORDER_STRONG), 1.3))
            p.setBrush(QColor(BG_SUBTLE))
            p.drawRoundedRect(3, 6, 9, 5, 2, 2)      # tab
            p.drawRoundedRect(3, 8, 18, 12, 2, 2)    # body
        else:
            accent = QColor(KS_RED) if kind == "mesh" else QColor(BORDER_STRONG)
            p.setPen(QPen(accent, 1.3))
            p.setBrush(QColor(BG_CARD))
            p.drawRoundedRect(5, 3, 14, 18, 2, 2)
            for y in (8, 12, 16):
                p.drawLine(8, y, 16, y)
        p.end()
        icon = QIcon(pm)
        self._cache[kind] = icon
        return icon

    def icon(self, arg):
        """QFileIconProvider hook — map files/folders to the flat glyphs."""
        if isinstance(arg, QFileInfo):
            if arg.isDir():
                return self._flat("folder")
            if arg.suffix().lower() in self._MESH_EXT:
                return self._flat("mesh")
            return self._flat("file")
        if arg in (QFileIconProvider.Folder, QFileIconProvider.Drive,
                   QFileIconProvider.Computer, QFileIconProvider.Network):
            return self._flat("folder")
        return self._flat("file")


# Object names of the stock QFileDialog chrome we hide (Qt5 internals — if a
# name is missing on some Qt build, we simply skip it).
_FILEDLG_HIDE = ("sidebar", "lookInLabel", "lookInCombo",
                 "backButton", "forwardButton", "toParentButton",
                 "newFolderButton", "listModeButton", "detailModeButton",
                 "fileTypeLabel", "fileTypeCombo")


class _FileCardFrame(QFrame):
    """Card holding the embedded QFileDialog. Esc must cancel from ANY focus
    position (path field, Up button, ...), not only when focus sits inside the
    dialog itself — otherwise the popup can't be dismissed by keyboard."""

    def __init__(self, parent, dlg):
        super().__init__(parent)
        self._dlg = dlg

    def keyPressEvent(self, ev):
        """Route Esc to the embedded dialog's reject() — the dialog only sees
        Esc itself when keyboard focus is inside it."""
        if ev.key() == Qt.Key_Escape:
            self._dlg.reject()
            return
        super().keyPressEvent(ev)


def _build_file_card(overlay, dlg, title, host):
    """Wrap the embedded QFileDialog in a card with a modern header."""
    dlg.setSidebarUrls([])
    for name in _FILEDLG_HIDE:
        child = dlg.findChild(QWidget, name)
        if child is not None:
            child.hide()

    card = _FileCardFrame(overlay, dlg)
    card.setObjectName("popupCard")
    card.setStyleSheet(f"""
        QFrame#popupCard {{
            background: {BG_CARD};
            border: 1px solid {BORDER_STRONG};
            border-radius: 8px;
        }}
        QLabel#fileCardTitle {{
            background: transparent; border: none;
            color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 700;
        }}
        QLineEdit#fileCardPath {{
            background: {BG_SUBTLE}; color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_STRONG}; border-radius: 4px;
            padding: 5px 8px; font-size: 12px;
            selection-background-color: {KS_RED}; selection-color: {TEXT_WHITE};
        }}
        QPushButton#fileCardNav {{
            background: {BG_CARD}; color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_STRONG}; border-radius: 4px;
            padding: 5px 12px; font-size: 12px; font-weight: 600;
        }}
        QPushButton#fileCardNav:hover {{ background: {BG_SUBTLE}; }}
    """ + STYLE_TOOLTIP)

    lay = QVBoxLayout(card)
    lay.setContentsMargins(16, 14, 16, 12)
    lay.setSpacing(10)

    title_lbl = QLabel(title)
    title_lbl.setObjectName("fileCardTitle")
    lay.addWidget(title_lbl)

    nav = QHBoxLayout()
    nav.setSpacing(8)
    path_edit = QLineEdit(dlg.directory().absolutePath())
    path_edit.setObjectName("fileCardPath")
    path_edit.setToolTip("Current folder — type a path and press Enter to jump there.")

    def _go_typed():
        p = path_edit.text().strip()
        if p and QDir(p).exists():
            dlg.setDirectory(p)
        else:
            path_edit.setText(dlg.directory().absolutePath())
    path_edit.returnPressed.connect(_go_typed)
    dlg.directoryEntered.connect(path_edit.setText)
    nav.addWidget(path_edit, 1)

    up_btn = QPushButton("↑ Up")
    up_btn.setObjectName("fileCardNav")
    up_btn.setCursor(Qt.ArrowCursor)
    up_btn.setToolTip("Go to the parent folder.")

    def _go_up():
        d = dlg.directory()
        if d.cdUp():
            dlg.setDirectory(d)
            path_edit.setText(d.absolutePath())
    up_btn.clicked.connect(_go_up)
    nav.addWidget(up_btn)

    newf = dlg.findChild(QWidget, "newFolderButton")
    if newf is not None:
        nf_btn = QPushButton("＋ New Folder")
        nf_btn.setObjectName("fileCardNav")
        nf_btn.setCursor(Qt.ArrowCursor)
        nf_btn.setToolTip("Create a new folder here.")
        nf_btn.clicked.connect(newf.click)      # reuse hidden stock action
        nav.addWidget(nf_btn)
    lay.addLayout(nav)

    dlg.setParent(card)
    dlg.setWindowFlags(Qt.Widget)                 # embed: not a real window
    lay.addWidget(dlg, 1)

    w = min(760, max(560, host.width() - 160))
    h = min(540, max(420, host.height() - 180))
    card.setFixedSize(w, h)
    card.setFocusProxy(dlg)                       # Esc / typing reach the dialog
    return card


def _run_file_dialog(parent, title, directory, name_filter, mode):
    """Show a file/folder picker as an in-window card (non-native QFileDialog
    embedded in a _PopupOverlay). Falls back to a real dialog when no visible
    host window exists. Backend for pick_open_file(s)/pick_existing_dir."""
    host = _host_window(parent)
    dlg = QFileDialog(None, title, directory, name_filter)
    dlg.setFileMode(mode)
    dlg.setOption(QFileDialog.DontUseNativeDialog, True)
    if mode == QFileDialog.Directory:
        dlg.setOption(QFileDialog.ShowDirsOnly, True)
    dlg._icon_provider = _FlatIconProvider()      # keep a live reference
    dlg.setIconProvider(dlg._icon_provider)
    if host is None or not host.isVisible():
        return dlg.selectedFiles() if dlg.exec_() else []
    overlay = _PopupOverlay(host)
    dlg.setObjectName("popupFileDlg")
    # Style EVERY inner widget explicitly — the embedded dialog otherwise
    # inherits the system (dark) palette and its views render black-on-black.
    dlg.setStyleSheet(f"""
        QFileDialog#popupFileDlg {{
            background: {BG_CARD};
            border: none;
        }}
        QFileDialog#popupFileDlg QWidget {{
            background: {BG_CARD};
            color: {TEXT_PRIMARY};
            font-size: 12px;
        }}
        QFileDialog#popupFileDlg QLabel {{
            background: transparent;
            color: {TEXT_MUTED};
        }}
        QFileDialog#popupFileDlg QLineEdit {{
            background: {BG_CARD};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_STRONG};
            border-radius: 4px;
            padding: 4px 8px;
            selection-background-color: {KS_RED};
            selection-color: {TEXT_WHITE};
        }}
        QFileDialog#popupFileDlg QComboBox {{
            background: {BG_CARD};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_STRONG};
            border-radius: 4px;
            padding: 4px 8px;
        }}
        QFileDialog#popupFileDlg QComboBox QAbstractItemView {{
            background: {BG_CARD};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_STRONG};
            selection-background-color: {KS_RED_LT};
            selection-color: {TEXT_PRIMARY};
        }}
        QFileDialog#popupFileDlg QTreeView,
        QFileDialog#popupFileDlg QListView {{
            background: {BG_CARD};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER};
            border-radius: 4px;
            alternate-background-color: {BG_SUBTLE};
        }}
        QFileDialog#popupFileDlg QTreeView::item,
        QFileDialog#popupFileDlg QListView::item {{
            padding: 3px 2px;
        }}
        QFileDialog#popupFileDlg QTreeView::item:selected,
        QFileDialog#popupFileDlg QListView::item:selected {{
            background: {KS_RED_LT};
            color: {TEXT_PRIMARY};
        }}
        QFileDialog#popupFileDlg QHeaderView::section {{
            background: {BG_SUBTLE};
            color: {TEXT_MUTED};
            border: none;
            border-bottom: 1px solid {BORDER};
            border-right: 1px solid {BORDER};
            padding: 4px 8px;
        }}
        QFileDialog#popupFileDlg QToolButton {{
            background: {BG_CARD};
            border: 1px solid {BORDER};
            border-radius: 4px;
            padding: 3px;
        }}
        QFileDialog#popupFileDlg QToolButton:hover {{
            background: {BG_SUBTLE};
            border-color: {BORDER_STRONG};
        }}
        QFileDialog#popupFileDlg QToolButton:disabled {{
            background: {BG_SUBTLE};
            border-color: {BORDER_SOFT};
        }}
        QFileDialog#popupFileDlg QPushButton {{
            background: {BG_CARD};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_STRONG};
            border-radius: 4px;
            padding: 6px 18px;
            font-weight: 600;
        }}
        QFileDialog#popupFileDlg QPushButton:hover {{
            background: {BG_SUBTLE};
        }}
        QFileDialog#popupFileDlg QPushButton:default {{
            background: {KS_RED};
            color: {TEXT_WHITE};
            border: none;
        }}
        QFileDialog#popupFileDlg QPushButton:default:hover {{
            background: {KS_RED_DARK};
        }}
        QFileDialog#popupFileDlg QScrollBar:vertical {{
            background: {BG_SUBTLE}; width: 10px; border: none;
        }}
        QFileDialog#popupFileDlg QScrollBar:horizontal {{
            background: {BG_SUBTLE}; height: 10px; border: none;
        }}
        QFileDialog#popupFileDlg QScrollBar::handle {{
            background: {BORDER_STRONG}; border-radius: 4px; min-height: 24px;
        }}
        QFileDialog#popupFileDlg QScrollBar::add-line,
        QFileDialog#popupFileDlg QScrollBar::sub-line {{
            width: 0px; height: 0px;
        }}
    """ + STYLE_TOOLTIP)
    card = _build_file_card(overlay, dlg, title, host)
    dlg.accepted.connect(lambda: overlay.finish(list(dlg.selectedFiles())))
    dlg.rejected.connect(lambda: overlay.finish([]))
    result = overlay.run(card)
    return result if result else []


def pick_open_file(parent, title, directory="", name_filter=""):
    """Centred in-window single-file picker; returns path or ''."""
    files = _run_file_dialog(parent, title, directory, name_filter,
                             QFileDialog.ExistingFile)
    return files[0] if files else ""


def pick_open_files(parent, title, directory="", name_filter=""):
    """Centred in-window multi-file picker; returns list of paths."""
    return _run_file_dialog(parent, title, directory, name_filter,
                            QFileDialog.ExistingFiles)


def pick_existing_dir(parent, title, directory=""):
    """Centred in-window directory picker; returns path or ''."""
    files = _run_file_dialog(parent, title, directory, "",
                             QFileDialog.Directory)
    return files[0] if files else ""


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


_pv_exe_searched: bool = False
_pv_exe_cache: Optional[str] = None


def find_paraview_exe() -> Optional[str]:
    """
    Find the newest installed ParaView executable visible from WSL.

    ParaView is installed on the Windows side (C:\\Program Files\\ParaView*).
    From WSL that path appears under /mnt/c/.  We glob for all versions and
    return the lexicographically last one, which corresponds to the highest
    version number because the directory names are versioned (e.g. ParaView-5.12).

    The result is cached on the first call so repeated lookups during the same
    session (landing page hero, utility card, Open ParaView button, post-run
    auto-launch) incur only one filesystem glob.
    """
    global _pv_exe_searched, _pv_exe_cache
    if not _pv_exe_searched:
        matches = sorted(glob.glob("/mnt/c/Program Files/ParaView*/bin/paraview.exe"))
        _pv_exe_cache = matches[-1] if matches else None
        _pv_exe_searched = True
    return _pv_exe_cache


def detect_openfoam_version() -> Optional[str]:
    """Version of the OpenFOAM install actually in use, e.g. '2506'.

    $WM_PROJECT_VERSION is set because the launcher sources the OpenFOAM
    bashrc before starting the GUI; if the GUI was started without it,
    fall back to the newest /usr/lib/openfoam/openfoam* directory."""
    env = os.environ.get("WM_PROJECT_VERSION", "").strip()
    if env:
        return env.lstrip("v")
    matches = sorted(glob.glob("/usr/lib/openfoam/openfoam[0-9]*"))
    if matches:
        return os.path.basename(matches[-1]).replace("openfoam", "")
    return None


def detect_ubuntu_version() -> Optional[str]:
    """Ubuntu release the GUI is running on, e.g. '24.04' (from os-release)."""
    try:
        with open("/etc/os-release") as f:
            info = dict(
                ln.strip().split("=", 1) for ln in f if "=" in ln)
    except OSError:
        return None
    ver = info.get("VERSION_ID", "").strip('"')
    return ver or None


def detect_python_version() -> str:
    """Running interpreter version, e.g. '3.12'."""
    import sys
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def detect_paraview_version() -> Optional[str]:
    """Version parsed from the detected ParaView install path, e.g. '5.13.1'.

    Returns None when no ParaView install is found; '?' when an install
    exists but the directory name carries no version number."""
    import re
    pv = find_paraview_exe()
    if not pv:
        return None
    m = re.search(r"ParaView-?(\d+\.\d+(?:\.\d+)?)", pv)
    return m.group(1) if m else "?"


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


def to_wsl_path(p: str) -> str:
    """Convert a Windows drive-letter path to its WSL /mnt/ equivalent.

    QFileDialog can return Windows-style paths (C:\\...) when running under
    WSLg or a native file dialog.  OpenFOAM executables only understand Linux
    paths, so any path that looks like a Windows drive path is remapped here.
    """
    import re
    if not p:
        return p
    m = re.match(r'^([A-Za-z]):[/\\](.*)$', p)
    if m:
        drive = m.group(1).lower()
        rest  = m.group(2).replace('\\', '/')
        return f'/mnt/{drive}/{rest}'
    return p.replace('\\', '/')


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


# ── 5. Plain-language error map ───────────────────────────────────────────────
# The log drawer shows raw OpenFOAM output, which is jargon-heavy and scary to a
# user who doesn't know CFD.  scan_log_for_fix() watches that output for known
# failure signatures and returns a plain-words fix to show in a red MessageBanner.
#
# Each entry: (keywords_all_lowercase, plain_fix).  A match requires EVERY
# keyword in the list to appear somewhere in the scanned text (case-insensitive
# substring).  Ordered specific → generic so the most precise fix wins.
OF_ERROR_MAP = [
    (["grid too fine"],
     "Your DX/DY/DZ is too small for this geometry, so the background mesh would "
     "have too many cells to build. DX/DY/DZ is the cell SIZE — increase it (use a "
     "bigger number) to make the mesh coarser, then click Generate again."),
    (["jinja2"],
     "The 'jinja2' package is missing in WSL. Open the Ubuntu terminal and run:  "
     "sudo apt-get install -y python3-jinja2  — then click Generate again."),
    (["command not found"],
     "An OpenFOAM command wasn't found — the OpenFOAM environment didn't load. "
     "Restart the app so WSL re-sources OpenFOAM, then try again."),
    (["blockmeshdict", "no such file"],
     "blockMeshDict is missing. Run the Background Mesh step first to build the "
     "background block, then run this step."),
    (["cannot find", "constant/polymesh"],
     "No background mesh found. Run the Background Mesh step first, then come back."),
    (["cannot read", "constant/polymesh"],
     "The background mesh is missing or damaged. Re-run the Background Mesh step."),
    (["cannot find file"],
     "A geometry file listed in the setup was not found. Check the STL/OBJ still "
     "exists under constant/ and click 'Refresh file list'."),
    (["cannot open file"],
     "A file couldn't be opened. Make sure the case folder and its STL files are "
     "readable and the paths have no typos."),
    (["locationinmesh"],
     "The 'location in mesh' point is wrong. It must sit in the fluid — inside the "
     "outer box AND outside every solid. Click 'Suggest point', then nudge it "
     "away from any solid body."),
    (["number of cells", "zero"],
     "The mesh came out empty. The 'location in mesh' point is almost certainly "
     "outside the domain — re-pick it inside the fluid."),
    (["selected 0 cells"],
     "The mesher kept no cells. Usually the 'location in mesh' point is outside "
     "the box, or refinement levels are too low. Fix the point first."),
    (["mesh has no cells"],
     "The mesh has no cells. Check the 'location in mesh' point is inside the "
     "fluid and that the background mesh exists."),
    (["negative volume"],
     "The mesh has bad (negative-volume) cells. Use smaller background cells "
     "(smaller DX/DY/DZ) or lower the refinement levels, then retry."),
    (["not enough layers"],
     "Some wall layers couldn't be added. Lower the layer count, or make the base "
     "mesh finer before adding layers."),
    (["is not closed"],
     "The STL surface has holes (not watertight). Repair it in your CAD tool so "
     "it's a fully closed shell, then re-export."),
    (["wrong token type"],
     "A settings file has a syntax error. If you hand-edited anything in system/, "
     "revert it and regenerate from this app."),
    (["keyword", "undefined"],
     "A required setting is missing from a dictionary. Regenerate it from this app "
     "instead of editing system/ files by hand."),
    (["foam fatal io error"],
     "OpenFOAM couldn't read a file it needs. Check the case has system/, "
     "constant/ and a background mesh, then retry."),
    (["foam fatal error"],
     "OpenFOAM stopped with a fatal error. Open the log below and read the last "
     "few red lines — the text right after 'FOAM FATAL ERROR' says what failed."),
]


def scan_log_for_fix(text: str) -> Optional[str]:
    """Return a plain-language fix for the first known failure signature found in
    `text`, or None if nothing matches. Case-insensitive; all keywords in an
    entry must be present."""
    if not text:
        return None
    low = text.lower()
    for keywords, fix in OF_ERROR_MAP:
        if all(k in low for k in keywords):
            return fix
    return None


# ── 6. MessageBanner ──────────────────────────────────────────────────────────

class MessageBanner(QWidget):
    """
    Reusable coloured status strip shared by both tabs (sits above the log
    drawer).  One widget, two looks:

      • show_error(msg)                         — red bar, ✕ icon, a plain-words fix
      • show_success(msg, action_label, cb)     — green bar, ✓ icon, optional
                                                   action button (e.g. "Continue →")

    Hidden until one of the show_* methods is called; a × button (or hide())
    dismisses it.  WA_StyledBackground is set so the #msg_banner background/border
    actually paints (Qt5 quirk — see PlusMinusSpinBox).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("msg_banner")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 8, 8)
        row.setSpacing(10)

        self._icon = QLabel("")
        self._icon.setStyleSheet("background: transparent; font-size: 15px; font-weight: bold;")
        self._icon.setAlignment(Qt.AlignTop)

        self._text = QLabel("")
        self._text.setWordWrap(True)
        self._text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._text.setStyleSheet("background: transparent; font-size: 13px;")

        self._action = QPushButton("")
        self._action.setCursor(Qt.PointingHandCursor)
        self._action.setVisible(False)
        self._action.clicked.connect(self._on_action)

        self._close = QPushButton("×")
        self._close.setFixedSize(22, 22)
        self._close.setCursor(Qt.PointingHandCursor)
        self._close.clicked.connect(self.hide_msg)

        row.addWidget(self._icon)
        row.addWidget(self._text, 1)
        row.addWidget(self._action)
        row.addWidget(self._close, 0, Qt.AlignTop)

        self._action_cb = None
        self.setVisible(False)

    def _apply(self, bg: str, fg: str, border: str):
        """Recolour the whole banner (background, text, icon, × button) for
        either the red error look or the green success look."""
        self.setStyleSheet(
            f"QWidget#msg_banner {{ background: {bg}; border: 1px solid {border};"
            f" border-radius: 6px; }}" + STYLE_TOOLTIP)
        self._text.setStyleSheet(f"color: {fg}; background: transparent; font-size: 13px;")
        self._icon.setStyleSheet(
            f"color: {fg}; background: transparent; font-size: 15px; font-weight: bold;")
        self._close.setStyleSheet(
            f"QPushButton {{ color: {fg}; background: transparent; border: none;"
            f" font-size: 16px; }} QPushButton:hover {{ color: {KS_RED}; }}"
            + STYLE_TOOLTIP)

    def show_error(self, message: str):
        """Red bar with a plain-words fix. No action button."""
        self._apply("#FEE2E2", "#991B1B", "#FECACA")
        self._icon.setText("✕")
        self._text.setText(message)
        self._action.setVisible(False)
        self._action_cb = None
        self.setVisible(True)

    def show_success(self, message: str, action_label: str = None, action_cb=None):
        """Green bar. If action_label is given, show a button that calls action_cb."""
        self._apply("#DCFCE7", "#166534", "#86EFAC")
        self._icon.setText("✓")
        self._text.setText(message)
        if action_label and action_cb:
            self._action.setText(action_label)
            self._action.setStyleSheet(STYLE_BTN_SMALL_RED)
            self._action.setVisible(True)
            self._action_cb = action_cb
        else:
            self._action.setVisible(False)
            self._action_cb = None
        self.setVisible(True)

    def _on_action(self):
        # Hide the banner BEFORE running the callback — the callback may switch
        # tabs, and a stale banner left visible on the old tab is confusing.
        cb = self._action_cb
        self.hide_msg()
        if cb:
            cb()

    def hide_msg(self):
        """Dismiss the banner (called by the × button or programmatically)."""
        self.setVisible(False)
