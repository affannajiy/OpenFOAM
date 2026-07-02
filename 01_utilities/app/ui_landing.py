#!/usr/bin/env python3
"""
ui_landing.py — Landing page shown before the utility UI on first launch.

LandingWidget is a full-window QWidget placed at index 0 of MainWindow's
_root_stack.  It emits continue_clicked(case_dir, util_id) when the user
clicks Continue; MainWindow connects this signal to show_utility().
"""

import os
import re
import json
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QComboBox, QScrollArea, QSizePolicy,
    QFileDialog, QStackedWidget, QMessageBox,
)
from PyQt5.QtCore import Qt, pyqtSignal

from ui_shared import (
    KS_RED, KS_RED_DARK, KS_RED_LT, KS_BLACK,
    BG_APP, BG_CARD, BG_SUBTLE,
    BORDER, BORDER_SOFT,
    TEXT_PRIMARY, TEXT_MUTED,
    STYLE_ENTRY, STYLE_COMBO, STYLE_SCROLL, STYLE_BTN_SMALL_RED, STYLE_BTN_GHOST,
    find_paraview_exe, build_card,
)

# ── OpenFOAM stub templates ───────────────────────────────────────────────────

_CONTROL_DICT = """\
FoamFile
{
    format      ascii;
    class       dictionary;
    object      controlDict;
}
application     blockMesh;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         1;
deltaT          1;
writeControl    timeStep;
writeInterval   1;
"""

_FV_SCHEMES = """\
FoamFile
{
    format      ascii;
    class       dictionary;
    object      fvSchemes;
}
ddtSchemes      { default Euler; }
gradSchemes     { default Gauss linear; }
divSchemes      { default none; }
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes   { default corrected; }
"""

_FV_SOLUTION = """\
FoamFile
{
    format      ascii;
    class       dictionary;
    object      fvSolution;
}
solvers {}
SIMPLE {}
"""

# ── Recents helpers ───────────────────────────────────────────────────────────

_RECENTS_PATH = os.path.expanduser("~/.openfoam_ui_recents.json")


def _load_recents() -> list:
    """Load the recents list from ~/.openfoam_ui_recents.json; returns [] on any error."""
    try:
        with open(_RECENTS_PATH, "r") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_recents(entries: list):
    """Persist the recents list to ~/.openfoam_ui_recents.json; silently ignores errors."""
    try:
        with open(_RECENTS_PATH, "w") as fh:
            json.dump(entries, fh, indent=2)
    except Exception:
        pass


def _prepend_recent(case_dir: str):
    """Insert case_dir at the front of the recents list, deduplicating and capping at 10."""
    name = os.path.basename(case_dir)
    entries = [e for e in _load_recents() if e.get("path") != case_dir]
    entries.insert(0, {"name": name, "path": case_dir})
    _save_recents(entries[:10])


def _case_status(path: str) -> str:
    """Return a short status label for a recent project entry."""
    if os.path.isfile(os.path.join(path, "constant", "polyMesh", "points")):
        return "Meshed"
    # Both "has controlDict" and "missing controlDict" show as Draft —
    # the pill colour distinguishes Meshed vs not, not case validity.
    return "Draft"


def _write_stub(path: str, content: str):
    """Write content to path only if the file does not already exist."""
    if not os.path.exists(path):
        with open(path, "w") as fh:
            fh.write(content)


# ── LandingWidget ─────────────────────────────────────────────────────────────

class LandingWidget(QWidget):
    """
    Full landing page shown on app start.

    Emits continue_clicked(case_dir, util_id) when the user presses Continue.
    """

    continue_clicked = pyqtSignal(str, int)
    return_clicked   = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode      = "new"
        self._util_id: Optional[int] = None
        self._open_path: Optional[str] = None

        self.setStyleSheet(f"background: {BG_APP};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Scrollable content ────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(STYLE_SCROLL)
        outer.addWidget(scroll, 1)

        inner = QWidget()
        inner.setStyleSheet(f"background: {BG_APP};")
        scroll.setWidget(inner)

        content = QVBoxLayout(inner)
        content.setContentsMargins(24, 24, 24, 24)
        content.setSpacing(16)

        # Return button — shown only when an active session exists
        self._return_btn = QPushButton("← Return to session")
        self._return_btn.setCursor(Qt.PointingHandCursor)
        self._return_btn.setStyleSheet(STYLE_BTN_GHOST)
        self._return_btn.setToolTip("Go back to the utility you already have open.")
        self._return_btn.setVisible(False)
        self._return_btn.clicked.connect(self.return_clicked)
        content.addWidget(self._return_btn, 0, Qt.AlignLeft)

        self._build_hero(content)
        self._build_columns(content)
        content.addStretch()

        self._update_preview()

    # ── Hero strip ────────────────────────────────────────────────────────────

    def _build_hero(self, content: QVBoxLayout):
        frame = QFrame()
        frame.setObjectName("landing_hero")
        frame.setStyleSheet(f"""
            QFrame#landing_hero {{
                background: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 6px;
            }}
        """)
        row = QHBoxLayout(frame)
        row.setContentsMargins(20, 20, 20, 20)
        row.setSpacing(20)

        # Left — title block
        left = QVBoxLayout()
        left.setSpacing(6)

        eyebrow = QLabel("W E L C O M E")
        eyebrow.setStyleSheet(
            f"color: {KS_RED}; font-family: Consolas; font-size: 9px;"
            " font-weight: bold; background: transparent;")
        left.addWidget(eyebrow)

        title = QLabel("Set Up a Meshing Case")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-family: 'Segoe UI'; font-size: 24px;"
            " font-weight: 300; background: transparent;")
        left.addWidget(title)

        subtitle = QLabel(
            "Pick a project, choose a utility, then generate. "
            "All commands run inside WSL with the OpenFOAM environment sourced.")
        subtitle.setStyleSheet(
            f"color: {TEXT_MUTED}; font-family: 'Segoe UI'; font-size: 12px;"
            " background: transparent;")
        subtitle.setWordWrap(True)
        left.addWidget(subtitle)

        row.addLayout(left, 1)

        # Right — environment metadata card
        meta = QFrame()
        meta.setObjectName("landing_meta")
        meta.setFixedWidth(260)
        meta.setStyleSheet(f"""
            QFrame#landing_meta {{
                background: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 6px;
            }}
        """)
        meta_v = QVBoxLayout(meta)
        meta_v.setContentsMargins(12, 12, 12, 12)
        meta_v.setSpacing(8)

        pv = find_paraview_exe()
        pv_text = "not found"
        if pv:
            m = re.search(r"ParaView-?(\d+\.\d+(?:\.\d+)?)", pv)
            pv_text = f"{m.group(1)} detected" if m else "detected"

        for key, val in [
            ("Working dir", os.path.expanduser("~/OpenFOAM")),
            ("OF binary",   "openfoam2506"),
            ("ParaView",    pv_text),
        ]:
            r = QHBoxLayout()
            k_lbl = QLabel(key)
            k_lbl.setStyleSheet(
                f"color: {TEXT_MUTED}; font-family: Consolas; font-size: 11px;"
                " background: transparent;")
            v_lbl = QLabel(val)
            v_lbl.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-family: Consolas; font-size: 11px;"
                " background: transparent;")
            v_lbl.setAlignment(Qt.AlignRight)
            r.addWidget(k_lbl)
            r.addStretch()
            r.addWidget(v_lbl)
            meta_v.addLayout(r)

        row.addWidget(meta)
        content.addWidget(frame)

    # ── Two-column layout ─────────────────────────────────────────────────────

    def _build_columns(self, content: QVBoxLayout):
        cols = QHBoxLayout()
        cols.setSpacing(20)

        proj_card, proj_body = build_card("01", "Project")
        proj_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._build_project_card(proj_body)

        util_card, util_body = build_card("02", "Utility")
        util_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._build_utility_card(util_body)

        cols.addWidget(proj_card)
        cols.addWidget(util_card)
        content.addLayout(cols)

    # ── Project card ──────────────────────────────────────────────────────────

    def _build_project_card(self, body: QVBoxLayout):
        # Segmented control
        seg = QFrame()
        seg.setObjectName("seg_ctl")
        seg.setFixedHeight(36)
        seg.setStyleSheet("QFrame#seg_ctl { background: #F4F4F4; border-radius: 6px; }")
        seg_row = QHBoxLayout(seg)
        seg_row.setContentsMargins(3, 3, 3, 3)
        seg_row.setSpacing(0)

        self._btn_new  = QPushButton("New project")
        self._btn_open = QPushButton("Open existing")
        self._btn_new.setToolTip("Create a fresh case folder with stub dictionaries.")
        self._btn_open.setToolTip("Point to an existing OpenFOAM case on disk.")
        for btn in (self._btn_new, self._btn_open):
            btn.setFixedHeight(30)
            btn.setCursor(Qt.PointingHandCursor)
        self._btn_new.clicked.connect(lambda: self._set_mode("new"))
        self._btn_open.clicked.connect(lambda: self._set_mode("open"))
        seg_row.addWidget(self._btn_new)
        seg_row.addWidget(self._btn_open)
        body.addWidget(seg)

        # Mode stack
        self._mode_stack = QStackedWidget()
        body.addWidget(self._mode_stack)

        new_page = QWidget()
        new_page.setStyleSheet(f"background: {BG_CARD};")
        new_v = QVBoxLayout(new_page)
        new_v.setContentsMargins(0, 0, 0, 0)
        new_v.setSpacing(10)
        self._build_new_project_form(new_v)
        self._mode_stack.addWidget(new_page)

        open_page = QWidget()
        open_page.setStyleSheet(f"background: {BG_CARD};")
        open_v = QVBoxLayout(open_page)
        open_v.setContentsMargins(0, 0, 0, 0)
        open_v.setSpacing(10)
        self._build_open_existing_form(open_v)
        self._mode_stack.addWidget(open_page)

        self._refresh_seg_control()

    def _build_new_project_form(self, vbox: QVBoxLayout):
        vbox.addWidget(self._field_label("P R O J E C T   N A M E"))
        self._name_edit = QLineEdit("my_case")
        self._name_edit.setStyleSheet(STYLE_ENTRY)
        self._name_edit.setToolTip("Folder name for the new case. Avoid spaces.")
        self._name_edit.textChanged.connect(self._update_preview)
        self._name_edit.textChanged.connect(self._update_continue_state)
        vbox.addWidget(self._name_edit)

        vbox.addWidget(self._field_label("L O C A T I O N"))
        loc_row = QHBoxLayout()
        loc_row.setSpacing(8)
        self._loc_edit = QLineEdit(os.path.expanduser("~/OpenFOAM"))
        self._loc_edit.setStyleSheet(STYLE_ENTRY)
        self._loc_edit.setToolTip(
            "Where the case folder is created. Must be reachable\n"
            "from WSL under /mnt/ (e.g. C:\\OpenFOAM).")
        self._loc_edit.textChanged.connect(self._update_preview)
        self._loc_edit.textChanged.connect(self._update_continue_state)
        browse_loc = QPushButton("Browse…")
        browse_loc.setFixedWidth(90)
        browse_loc.setCursor(Qt.PointingHandCursor)
        browse_loc.setStyleSheet(STYLE_BTN_SMALL_RED)
        browse_loc.setToolTip("Pick the parent folder for the new case.")
        browse_loc.clicked.connect(self._browse_location)
        loc_row.addWidget(self._loc_edit, 1)
        loc_row.addWidget(browse_loc)
        vbox.addLayout(loc_row)

        vbox.addWidget(self._field_label("T E M P L A T E"))
        self._template_combo = QComboBox()
        self._template_combo.setStyleSheet(STYLE_COMBO)
        self._template_combo.setToolTip(
            "What to put in the new case:\n"
            "Empty     = folders + stub dicts only\n"
            "From STL  = also fill triSurface/ from an STL\n"
            "Copy      = clone an existing case")
        self._template_combo.addItems([
            "Empty case (constant/, system/, 0/)",
            "From STL — auto-populate triSurface/",
            "Copy from existing case…",
        ])
        vbox.addWidget(self._template_combo)

        vbox.addWidget(self._field_label("W I L L   C R E A T E :"))
        preview_frame = QFrame()
        preview_frame.setObjectName("preview_frame")
        preview_frame.setStyleSheet(f"""
            QFrame#preview_frame {{
                background: #F9FAFB;
                border: 1px solid {BORDER};
                border-radius: 6px;
            }}
        """)
        pf_v = QVBoxLayout(preview_frame)
        pf_v.setContentsMargins(10, 10, 10, 10)
        self._preview_lbl = QLabel()
        self._preview_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-family: Consolas; font-size: 10px;"
            " background: transparent;")
        self._preview_lbl.setTextFormat(Qt.PlainText)
        pf_v.addWidget(self._preview_lbl)
        vbox.addWidget(preview_frame)

    def _build_open_existing_form(self, vbox: QVBoxLayout):
        browse_btn = QPushButton("Browse for case folder…")
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.setStyleSheet(STYLE_BTN_SMALL_RED)
        browse_btn.setToolTip(
            "Pick an existing case folder.\n"
            "Must contain system/controlDict.")
        browse_btn.clicked.connect(self._browse_open_case)
        vbox.addWidget(browse_btn)

        self._open_path_lbl = QLabel("No folder selected")
        self._open_path_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-family: Consolas; font-size: 10px;"
            " background: transparent;")
        vbox.addWidget(self._open_path_lbl)

        vbox.addWidget(self._field_label("R E C E N T   P R O J E C T S"))

        recents_scroll = QScrollArea()
        recents_scroll.setWidgetResizable(True)
        recents_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        recents_scroll.setStyleSheet(f"""
            QScrollArea {{
                background: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 6px;
            }}
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
        """)
        recents_scroll.setMinimumHeight(168)

        self._recents_inner = QWidget()
        self._recents_inner.setStyleSheet(f"background: {BG_CARD}; border: none;")
        self._recents_vbox = QVBoxLayout(self._recents_inner)
        self._recents_vbox.setContentsMargins(6, 6, 6, 6)
        self._recents_vbox.setSpacing(4)

        recents_scroll.setWidget(self._recents_inner)
        vbox.addWidget(recents_scroll)

        self._recents = _load_recents()
        self._selected_row_frame = None
        self._rebuild_recents_list()

    def _rebuild_recents_list(self):
        """Repopulate the recents scroll area from self._recents.

        Resets _selected_row_frame, then re-highlights the row whose path
        matches self._open_path so selection state survives a full rebuild
        (e.g. after deleting an entry or switching mode).
        """
        self._selected_row_frame = None
        while self._recents_vbox.count():
            item = self._recents_vbox.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for entry in self._recents:
            row = self._make_recent_row(entry)
            self._recents_vbox.addWidget(row)
            if entry.get("path") == self._open_path:
                row.setStyleSheet(
                    f"QFrame#recent_row {{ background: {KS_RED_LT}; border: 1px solid {KS_RED};"
                    " border-radius: 4px; }}")
                self._selected_row_frame = row
        self._recents_vbox.addStretch()

    def _make_recent_row(self, entry: dict) -> QFrame:
        path   = entry.get("path", "")
        name   = entry.get("name", os.path.basename(path))
        status = _case_status(path)

        row_frame = QFrame()
        row_frame.setObjectName("recent_row")
        row_frame.setFixedHeight(56)
        row_frame.setCursor(Qt.PointingHandCursor)
        row_frame.setStyleSheet(
            f"QFrame#recent_row {{ background: {BG_CARD}; border: 1px solid {BORDER};"
            " border-radius: 4px; }}")

        row_h = QHBoxLayout(row_frame)
        row_h.setContentsMargins(10, 0, 10, 0)
        row_h.setSpacing(8)

        left = QVBoxLayout()
        left.setSpacing(2)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-family: 'Segoe UI'; font-size: 12px;"
            " font-weight: 600; background: transparent; border: none;")

        path_lbl = QLabel(path)
        path_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-family: Consolas; font-size: 10px;"
            " background: transparent; border: none;")

        left.addWidget(name_lbl)
        left.addWidget(path_lbl)

        if status == "Meshed":
            pill_ss = ("background: #D1FAE5; color: #065F46;"
                       " font-family: Consolas; font-size: 9px;"
                       " border-radius: 4px; padding: 2px 0px; border: none;")
        else:
            pill_ss = (f"background: #F3F4F6; color: {TEXT_MUTED};"
                       " font-family: Consolas; font-size: 9px;"
                       " border-radius: 4px; padding: 2px 0px; border: none;")

        pill = QLabel(status)
        pill.setFixedWidth(60)
        pill.setAlignment(Qt.AlignCenter)
        pill.setStyleSheet(pill_ss)

        del_btn = QPushButton("×")
        del_btn.setFixedSize(24, 24)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setToolTip("Remove from recents (does not delete the folder).")
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {TEXT_MUTED};
                font-size: 16px;
            }}
            QPushButton:hover {{ color: {KS_RED}; }}
        """)
        del_btn.clicked.connect(lambda _checked, p=path: self._on_recent_delete(p))

        row_h.addLayout(left, 1)
        row_h.addWidget(pill)
        row_h.addWidget(del_btn)

        # Assign the click handler directly rather than subclassing QFrame —
        # each row is a plain QFrame created dynamically, and monkey-patching
        # mousePressEvent is the simplest way to bind per-row data (path, frame).
        row_frame.mousePressEvent = (
            lambda _event, p=path, f=row_frame: self._on_recent_row_click(p, f)
        )
        return row_frame

    def _on_recent_row_click(self, path: str, frame: QFrame):
        if self._selected_row_frame and self._selected_row_frame is not frame:
            self._selected_row_frame.setStyleSheet(
                f"QFrame#recent_row {{ background: {BG_CARD}; border: 1px solid {BORDER};"
                " border-radius: 4px; }}")
        frame.setStyleSheet(
            f"QFrame#recent_row {{ background: {KS_RED_LT}; border: 1px solid {KS_RED};"
            " border-radius: 4px; }}")
        self._selected_row_frame = frame
        self._open_path = path
        self._open_path_lbl.setText(path)
        self._open_path_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-family: Consolas; font-size: 10px;"
            " background: transparent;")
        self._update_continue_state()

    def _on_recent_delete(self, path: str):
        self._recents = [e for e in self._recents if e.get("path") != path]
        _save_recents(self._recents)
        if self._open_path == path:
            self._open_path = None
            self._open_path_lbl.setText("No folder selected")
            self._open_path_lbl.setStyleSheet(
                f"color: {TEXT_MUTED}; font-family: Consolas; font-size: 10px;"
                " background: transparent;")
            self._update_continue_state()
        self._rebuild_recents_list()

    # ── Utility card ──────────────────────────────────────────────────────────

    def _build_utility_card(self, body: QVBoxLayout):
        self._util_frames: list[QFrame] = []

        for uid, title, chip, desc in [
            (0, "Background Mesh",    "~5–30s",  "Generate blockMesh from STL bounding box"),
            (1, "SnappyHexMesh Dict", "~2–20m",  "Build snappyHexMeshDict and run mesh"),
        ]:
            card = self._make_util_selector(uid, title, chip, desc)
            self._util_frames.append(card)
            body.addWidget(card)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"QFrame {{ background: {BORDER}; }}")
        body.addWidget(sep)

        env_lbl = QLabel("E N V I R O N M E N T")
        env_lbl.setAlignment(Qt.AlignLeft)
        env_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-family: Consolas; font-size: 9px;"
            " font-weight: bold; background: transparent;")
        body.addWidget(env_lbl)

        pv_ok = bool(find_paraview_exe())
        left_col  = [("OpenFOAM 2506", True), ("ParaView 5.13", pv_ok)]
        right_col = [("WSL Ubuntu",    True), ("Python 3.10",   True)]

        env_row = QHBoxLayout()
        env_row.setSpacing(16)

        for col_items in (left_col, right_col):
            col_vbox = QVBoxLayout()
            col_vbox.setSpacing(6)
            for lbl_text, ok in col_items:
                item_h = QHBoxLayout()
                item_h.setSpacing(6)
                dot = QLabel("●")
                dot.setStyleSheet(
                    f"color: {'#22C55E' if ok else '#9CA3AF'};"
                    " font-size: 11px; background: transparent;")
                text = QLabel(lbl_text)
                text.setStyleSheet(
                    f"color: {TEXT_PRIMARY}; font-family: 'Segoe UI';"
                    " font-size: 12px; background: transparent;")
                item_h.addWidget(dot)
                item_h.addWidget(text)
                col_vbox.addLayout(item_h)
            env_row.addLayout(col_vbox)

        env_row.addStretch()
        body.addLayout(env_row)
        body.addStretch()

    def _make_util_selector(self, uid: int, title: str, chip: str, desc: str) -> QFrame:
        card = QFrame()
        card.setObjectName(f"util_card_{uid}")
        card.setCursor(Qt.PointingHandCursor)
        card.setToolTip(f"{desc}. Click to select, double-click to open.")
        self._style_util_card(card, selected=False)

        row = QHBoxLayout(card)
        row.setContentsMargins(14, 14, 14, 14)
        row.setSpacing(10)

        left = QVBoxLayout()
        left.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_lbl = QLabel(title)
        title_lbl.setObjectName(f"util_title_{uid}")
        title_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-family: 'Segoe UI'; font-size: 13px;"
            " font-weight: 600; background: transparent; border: none;")
        chip_lbl = QLabel(chip)
        chip_lbl.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_MUTED}; font-family: Consolas; font-size: 10px;
                background: #F4F4F4; border: none; border-radius: 4px; padding: 2px 6px;
            }}
        """)
        title_row.addWidget(title_lbl)
        title_row.addWidget(chip_lbl)
        title_row.addStretch()
        left.addLayout(title_row)

        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-family: 'Segoe UI'; font-size: 11px;"
            " background: transparent; border: none;")
        left.addWidget(desc_lbl)

        arrow = QLabel("→")
        arrow.setObjectName(f"util_arrow_{uid}")
        arrow.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 14px; background: transparent; border: none;")

        row.addLayout(left, 1)
        row.addWidget(arrow)

        card.mousePressEvent = lambda _event, i=uid: self._select_util(i)
        card.mouseDoubleClickEvent = lambda _event, i=uid: self._on_util_double_click(i)
        return card

    def _style_util_card(self, card: QFrame, selected: bool):
        name = card.objectName()
        if selected:
            card.setStyleSheet(f"""
                QFrame#{name} {{
                    border: 2px solid {KS_RED};
                    border-radius: 6px;
                    background: {KS_RED_LT};
                }}
            """)
        else:
            card.setStyleSheet(f"""
                QFrame#{name} {{
                    border: 1px solid {BORDER};
                    border-radius: 6px;
                    background: {BG_CARD};
                }}
                QFrame#{name}:hover {{
                    border: 1px solid #D1D5DB;
                }}
            """)

    def _select_util(self, uid: int):
        self._util_id = uid
        for i, card in enumerate(self._util_frames):
            selected = (i == uid)
            self._style_util_card(card, selected)
            arrow = card.findChild(QLabel, f"util_arrow_{i}")
            if arrow:
                color = KS_RED if selected else TEXT_MUTED
                arrow.setStyleSheet(
                    f"color: {color}; font-size: 14px; background: transparent;"
                    " border: none;")
        self._update_continue_state()

    def _on_util_double_click(self, uid: int):
        self._select_util(uid)
        self._on_continue()

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _field_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-family: Consolas; font-size: 9px;"
            " font-weight: 600; background: transparent;")
        return lbl

    @staticmethod
    def _ghost_btn_ss() -> str:
        return f"""
            QPushButton {{
                background: {BG_SUBTLE};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 7px 12px;
                font-family: 'Segoe UI';
                font-size: 13px;
            }}
            QPushButton:hover {{ border-color: {TEXT_MUTED}; }}
        """

    def _set_mode(self, mode: str):
        self._mode = mode
        self._mode_stack.setCurrentIndex(0 if mode == "new" else 1)
        self._refresh_seg_control()
        self._update_continue_state()

    def _refresh_seg_control(self):
        active_ss = (
            f"QPushButton {{ background: {BG_CARD}; border: 1px solid {BORDER};"
            f" border-radius: 4px; color: {TEXT_PRIMARY};"
            f" font-family: 'Segoe UI'; font-size: 12px; font-weight: 600; }}"
        )
        inactive_ss = (
            f"QPushButton {{ background: transparent; border: none;"
            f" color: {TEXT_MUTED}; font-family: 'Segoe UI'; font-size: 12px; }}"
        )
        if self._mode == "new":
            self._btn_new.setStyleSheet(active_ss)
            self._btn_open.setStyleSheet(inactive_ss)
        else:
            self._btn_new.setStyleSheet(inactive_ss)
            self._btn_open.setStyleSheet(active_ss)

    def _update_preview(self):
        name = self._name_edit.text().strip() or "my_case"
        loc  = self._loc_edit.text().strip() or "~"
        loc  = loc.rstrip("/\\")
        tree = (
            f"{loc}/{name}/\n"
            f"├── constant/\n"
            f"│   └── triSurface/        ← drop STL here\n"
            f"├── system/\n"
            f"│   ├── controlDict\n"
            f"│   ├── fvSchemes\n"
            f"│   └── fvSolution\n"
            f"└── 0/"
        )
        self._preview_lbl.setText(tree)

    def _browse_location(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select project location",
            os.path.expanduser(self._loc_edit.text()))
        if d:
            self._loc_edit.setText(d)

    def _browse_open_case(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select OpenFOAM case folder", os.path.expanduser("~"))
        if not d:
            return
        if not os.path.isfile(os.path.join(d, "system", "controlDict")):
            QMessageBox.warning(
                self, "Not a valid case",
                f"The selected folder does not contain system/controlDict:\n{d}")
            return
        self._open_path = d
        self._open_path_lbl.setText(d)
        self._open_path_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-family: Consolas; font-size: 10px;"
            " background: transparent;")
        self._update_continue_state()

    def _update_continue_state(self):
        # Continue is always enabled — input validation runs in _on_continue,
        # not here.  This hook exists so subclasses or future revisions can
        # enable/disable the button reactively without changing _on_continue.
        pass

    # ── Continue action ───────────────────────────────────────────────────────

    def _on_continue(self):
        if self._mode == "new":
            name     = self._name_edit.text().strip()
            location = os.path.expanduser(self._loc_edit.text().strip())
            if not name:
                QMessageBox.warning(self, "Missing name", "Please enter a project name.")
                return
            case_dir = os.path.join(location, name)
            try:
                os.makedirs(os.path.join(case_dir, "constant", "triSurface"), exist_ok=True)
                os.makedirs(os.path.join(case_dir, "system"), exist_ok=True)
                os.makedirs(os.path.join(case_dir, "0"),        exist_ok=True)
                _write_stub(os.path.join(case_dir, "system", "controlDict"), _CONTROL_DICT)
                _write_stub(os.path.join(case_dir, "system", "fvSchemes"),   _FV_SCHEMES)
                _write_stub(os.path.join(case_dir, "system", "fvSolution"),  _FV_SOLUTION)
                _write_stub(os.path.join(case_dir, f"{name}.foam"),           "")
            except Exception as exc:
                QMessageBox.critical(self, "Error creating case", str(exc))
                return
        else:
            case_dir = self._open_path
            if not case_dir:
                QMessageBox.warning(
                    self, "No project selected",
                    "Please browse to or select an OpenFOAM case folder first.")
                return
            if not os.path.isfile(os.path.join(case_dir, "system", "controlDict")):
                QMessageBox.warning(
                    self, "Invalid case",
                    "system/controlDict not found in the selected folder.")
                return

        _prepend_recent(case_dir)
        self.continue_clicked.emit(case_dir, self._util_id)

    def refresh_recents(self):
        """Re-read ~/.openfoam_ui_recents.json and repopulate the list."""
        if hasattr(self, "_recents_vbox"):
            self._recents = _load_recents()
            self._rebuild_recents_list()

    def set_has_active_session(self, active: bool, tab_name: str = ""):
        """Show or hide the Return button based on whether a utility session is open."""
        self._return_btn.setVisible(active)
        if active and tab_name:
            self._return_btn.setText(f"← Return to {tab_name}")
