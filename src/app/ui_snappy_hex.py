#!/usr/bin/env python3
"""
ui_snappy_hex.py — Tab 2: SnappyHexMesh Dict generator and mesh runner.

Five-section scrollable card form.  On "Generate Dict & Run snappyHexMesh"
the GUI builds a config dict and hands it to snappy_generator.generate_and_run(),
which renders snappyHexMeshDict from a Jinja2 template in one pass, records the
inputs to <case>/snappy_inputs.json, and runs snappyHexMesh.

Thread safety
-------------
All widget reads happen in _collect_data() on the GUI thread before the worker
starts.  The worker receives a plain Python dict — no Qt objects.

Section layout
--------------
  01 Geometry     — file table with per-row surface type / refinement / vol dir
                    + standard shapes (Box / Cylinder / Sphere)
  02 Castellation — geometry unit, nCellsBetweenLevels, locationInMesh
  03 Snap         — automatic (implicit) feature snapping, always on
  04 Layers       — per-patch nSurfaceLayers (auto-populated from Section 01)
  05 Generate     — single "Generate Dict & Run snappyHexMesh" button
"""

import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QScrollArea, QFrame,
    QCheckBox, QSizePolicy,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QEvent, QFileSystemWatcher

from ui_shared import (
    KS_RED, BG_APP, BG_CARD, BG_SUBTLE, BORDER, BORDER_SOFT,
    TEXT_PRIMARY, TEXT_MUTED, TEXT_WHITE, FONT_UI, FONT_MONO,
    STYLE_BTN_PRIMARY, STYLE_BTN_SMALL_GHOST, STYLE_BTN_SMALL_RED,
    STYLE_ENTRY, STYLE_COMBO, STYLE_SCROLL, STYLE_CHECKBOX, STYLE_TOOLTIP,
    build_card, to_wsl_path, PlusMinusSpinBox, ChevronComboBox, get_stl_zone_names,
    find_paraview_exe, make_info_icon, MessageBanner, scan_log_for_fix,
    load_prefs, save_prefs, msg_warning, msg_critical,
    pick_open_files, pick_existing_dir,
)

try:
    import snappy_generator
    _BACKEND_OK  = True
    _BACKEND_ERR = ""
except Exception as _imp_exc:
    _BACKEND_OK  = False
    _BACKEND_ERR = str(_imp_exc)

_GEOM_UNITS = ["mm", "m", "cm", "um", "in", "ft"]
_SURF_TYPES = ["None", "Boundary", "FaceZone"]
_VOL_DIRS   = ["None", "Inside", "Outside"]

# ASCII STL vertex line — shared by the smart-defaults bbox scan and the
# locationInMesh suggester.
_VERTEX_RE = re.compile(
    r'vertex\s+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)'
    r'\s+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)'
    r'\s+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)')


# ── Worker thread ─────────────────────────────────────────────────────────────────

class _SnappyWorker(QThread):
    """
    Runs snappy_generator.generate_and_run() in a background thread.
    Communicates with the UI exclusively via Qt signals.
    """
    log_signal      = pyqtSignal(str, str)   # message, tag
    finished_signal = pyqtSignal(bool)        # success

    def __init__(self, config: dict, case_dir: str):
        super().__init__()
        self.config   = config
        self.case_dir = case_dir

    def run(self):
        """Thread entry: run the backend; any exception becomes a red log line
        + finished_signal(False) instead of crashing the app."""
        try:
            success = snappy_generator.generate_and_run(
                self.config, self.case_dir, self._log)
            self.finished_signal.emit(success)
        except Exception as exc:
            self._log(f"Fatal error: {exc}", "error")
            self.finished_signal.emit(False)

    def _log(self, message: str, tag: str = "info"):
        """Adapter so the backend's log_cb(message, tag) lands on a Qt signal."""
        self.log_signal.emit(message, tag)


# ── Tab widget ────────────────────────────────────────────────────────────────────

class SnappyHexWidget(QWidget):
    """Tab 2 widget — SnappyHexMesh Dict generator and mesh runner."""

    def __init__(self, log_drawer, parent=None):
        super().__init__(parent)
        self._log = log_drawer
        self._cwd = os.getcwd()

        # (fname, full_path, widgets_dict)
        self._file_rows: list = []
        # (shape_dict) — each has type_combo, vol_dir_combo, vol_level_sp, widgets, fields_layout
        self._shape_widgets: list = []
        # patch_name → PlusMinusSpinBox (nSurfaceLayers)
        self._layer_patch_widgets: dict = {}
        # full_path → list[str] zone names; avoids re-reading STL files on every
        # Surface Type change or layer-patch refresh within the same session.
        self._zone_name_cache: dict = {}
        # full_path → bounding-box volume; used by the smart per-row defaults
        # (largest STL = outer shell) so files are only parsed once per case.
        self._stl_vol_cache: dict = {}

        # Widget references set to None before _build() runs.  Methods called
        # during construction (e.g. _refresh_file_list → _refresh_layer_patches)
        # guard with "if self._xxx" so they are safe before the widgets exist.
        self._cwd_lbl               = None
        self._file_table_layout     = None
        self._num_shapes_sp         = None
        self._shapes_container_layout = None
        self._geom_unit_combo       = None
        self._cancel_btn            = None
        self._ncbl_sp               = None
        self._loc_x_sp              = None
        self._loc_y_sp              = None
        self._loc_z_sp              = None
        self._location_warn         = None
        self._snap_implicit_cb      = None
        self._add_layers_cb         = None
        self._layer_details_w       = None
        self._layer_details_layout  = None
        self._run_btn               = None
        self._dict_banner           = None
        self._time_dirs_lbl         = None
        self._open_paraview_cb      = None
        self._msg_banner            = None
        self._run_log: list         = []   # collected output for error scanning

        # Auto-rescan: a QFileSystemWatcher on constant/ (+ subdirs) fires when
        # the user drops in / removes / edits an STL from Explorer, so the file
        # table refreshes itself. Bursts of change events are debounced through
        # a single-shot timer so a multi-file paste triggers one rebuild.
        self._fs_watcher = QFileSystemWatcher(self)
        self._fs_watcher.directoryChanged.connect(self._on_constant_changed)
        self._fs_watcher.fileChanged.connect(self._on_constant_changed)
        self._watch_debounce = QTimer(self)
        self._watch_debounce.setSingleShot(True)
        self._watch_debounce.setInterval(600)
        self._watch_debounce.timeout.connect(self._auto_refresh_files)

        self.setStyleSheet(f"background: {BG_APP};")
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────────

    def _build(self):
        """Assemble the tab: slim working-directory bar on top, then the five
        section cards (01–05) inside one vertical scroll area."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # CWD slim bar
        cwd_bar = QWidget()
        cwd_bar.setStyleSheet(f"background: {BG_CARD}; border-bottom: 1px solid {BORDER};")
        cwd_bar.setFixedHeight(40)
        cwd_row = QHBoxLayout(cwd_bar)
        cwd_row.setContentsMargins(20, 0, 20, 0)
        cwd_row.setSpacing(10)
        cwd_lbl = QLabel("Working directory:")
        cwd_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px; background: transparent;")
        self._cwd_lbl = QLabel(self._cwd)
        self._cwd_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-family: {FONT_MONO}; font-size: 11px; background: transparent;")
        self._cwd_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        change_btn = QPushButton("Change…")
        change_btn.setStyleSheet(STYLE_BTN_SMALL_RED)
        change_btn.setToolTip("Switch to a different case folder without leaving this tab.")
        change_btn.clicked.connect(self._change_cwd)
        cwd_row.addWidget(cwd_lbl)
        cwd_row.addWidget(self._cwd_lbl)
        cwd_row.addWidget(change_btn)
        outer.addWidget(cwd_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(STYLE_SCROLL)
        outer.addWidget(scroll)

        self._content = QWidget()
        self._content.setStyleSheet(f"background: {BG_APP};")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(24, 16, 24, 24)
        self._content_layout.setSpacing(14)
        scroll.setWidget(self._content)

        self._build_sec1()
        self._build_sec2()
        self._build_sec3()
        self._build_sec4()
        self._build_sec5()
        self._content_layout.addStretch()

        # Restore last-used non-case-specific settings from the per-user prefs
        # file (unit, nCellsBetweenLevels, layers toggle).  Case-specific values
        # (locationInMesh, file table) are deliberately not persisted.
        prefs = load_prefs()
        unit = prefs.get("snappy_unit")
        if unit in _GEOM_UNITS and self._geom_unit_combo:
            self._geom_unit_combo.setCurrentText(unit)
        ncbl = prefs.get("snappy_ncbl")
        if isinstance(ncbl, int) and self._ncbl_sp:
            self._ncbl_sp.setValue(ncbl)
        if isinstance(prefs.get("snappy_add_layers"), bool) and self._add_layers_cb:
            self._add_layers_cb.setChecked(prefs["snappy_add_layers"])

    # ── Shared helpers ─────────────────────────────────────────────────────────────

    def _label_small(self, text: str) -> QLabel:
        """Small grey letter-spaced caption used above field groups."""
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-family: {FONT_UI}; font-size: 11px;"
            " font-weight: 600; letter-spacing: 0.4px; background: transparent;")
        return lbl

    def _sub_card(self, parent_layout: QVBoxLayout, title: str) -> QVBoxLayout:
        """Small card-inside-a-card (red title strip + white body) used for
        each standard shape. Returns the body layout to fill."""
        wrapper = QFrame()
        wrapper.setObjectName("sub_card")
        wrapper.setStyleSheet(f"""
            QFrame#sub_card {{
                background: {BG_CARD};
                border: 1px solid {BORDER_SOFT};
                border-radius: 4px;
                margin-top: 4px;
            }}
        """)
        vbox = QVBoxLayout(wrapper)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        hdr_w = QWidget()
        hdr_w.setStyleSheet(f"background: {BG_SUBTLE}; border-radius: 4px 4px 0 0;")
        hdr_row = QHBoxLayout(hdr_w)
        hdr_row.setContentsMargins(12, 4, 12, 4)
        ttl_lbl = QLabel(title)
        ttl_lbl.setStyleSheet(
            f"color: {KS_RED}; font-size: 12px; font-weight: 600; background: transparent;")
        hdr_row.addWidget(ttl_lbl)
        hdr_row.addStretch()
        vbox.addWidget(hdr_w)

        body_w = QWidget()
        body_w.setStyleSheet(f"background: {BG_CARD};")
        body_vbox = QVBoxLayout(body_w)
        body_vbox.setContentsMargins(12, 8, 12, 10)
        body_vbox.setSpacing(6)
        vbox.addWidget(body_w)

        parent_layout.addWidget(wrapper)
        return body_vbox

    def _make_coord_spinbox(self) -> PlusMinusSpinBox:
        """4-decimal float picker used for the locationInMesh x/y/z fields."""
        sp = PlusMinusSpinBox(decimals=4, step=1)
        sp.setRange(-1e9, 1e9)
        sp.setValue(0.0)
        sp.setFixedWidth(168)
        return sp

    def _resize_file_table_scroll(self):
        """Size the file-table scroll area to its content.

        setWidgetResizable(False) means Qt won't resize the child when its
        content — or the viewport — changes, so we drive both dimensions:
        - WIDTH: stretch the child to fill the viewport (so the table spans
          the whole gray card area, not just its scrunched minimum). If the
          fixed columns need more room than the viewport, keep the larger
          content width so they scroll instead of clip.
        - HEIGHT: grow to fit the rows, else the child stays near-zero and
          the table looks empty.
        The FILE column has an Expanding size policy, so the extra width
        lands there and the table breathes across the card."""
        if not self._file_table_w:
            return
        self._file_table_w.adjustSize()
        hint = self._file_table_w.sizeHint()
        vp_w = self._file_table_scroll.viewport().width()
        overflow = hint.width() > vp_w
        w = max(hint.width(), vp_w)
        self._file_table_w.resize(w, hint.height())
        # +18 only when a horizontal scrollbar actually shows, so the bottom
        # row isn't clipped by it; no padding when the table fits the width.
        self._file_table_scroll.setFixedHeight(
            max(hint.height(), 1) + (18 if overflow else 0))

    def eventFilter(self, obj, event):
        # The scroll area doesn't resize its (non-resizable) child on its own,
        # so re-fit the table whenever the viewport width changes with the
        # window — keeps it filling the card at every window size.
        if obj is self._file_table_scroll and event.type() == QEvent.Resize:
            QTimer.singleShot(0, self._resize_file_table_scroll)
        return super().eventFilter(obj, event)

    def _stl_bbox_volume(self, path: str) -> float:
        """Bounding-box volume of an ASCII STL. Returns 0.0 when unparseable
        (binary STL, missing file) — such files are never picked as the shell."""
        try:
            with open(path, "r", errors="ignore") as f:
                text = f.read()
            verts = _VERTEX_RE.findall(text)
            if not verts:
                return 0.0
            xs = [float(v[0]) for v in verts]
            ys = [float(v[1]) for v in verts]
            zs = [float(v[2]) for v in verts]
            return (max(xs) - min(xs)) * (max(ys) - min(ys)) * (max(zs) - min(zs))
        except Exception:
            return 0.0

    # ── Section 1: Geometry ────────────────────────────────────────────────────────

    def _build_sec1(self):
        """Section 01 — Geometry: the horizontally-scrollable file table (one
        row per STL/OBJ under constant/) plus the standard-shapes picker."""
        card, body = build_card("01", "Geometry", tip=(
            "List of shapes to mesh: STL/OBJ files found under\n"
            "constant/, plus standard shapes you add. Set each\n"
            "one's surface type and refinement here."))
        self._content_layout.addWidget(card)
        self._sec1_body = body

        desc = QLabel(
            "Files found under constant/ — set Surface Type and Refinement levels for each.\n"
            "Smart defaults: the largest file is treated as the outer shell (Boundary); "
            "all others as solid bodies inside it (FaceZone + Cell Zone). Adjust as needed.")
        desc.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px; background: transparent;")
        desc.setWordWrap(True)
        body.addWidget(desc)


        # Wrapped in its own horizontal-scrolling area so the fixed-width
        # columns (Surface Type / Cell Zone / Min / Max / Vol Dir / V.Lvl)
        # never get clipped by the window edge — they scroll into view
        # instead, regardless of window size.
        self._file_table_w = QWidget()
        self._file_table_w.setStyleSheet(f"background: {BG_CARD};")
        self._file_table_layout = QVBoxLayout(self._file_table_w)
        self._file_table_layout.setContentsMargins(0, 0, 0, 0)
        self._file_table_layout.setSpacing(0)

        file_table_scroll = QScrollArea()
        file_table_scroll.setWidgetResizable(False)
        file_table_scroll.setFrameShape(QFrame.NoFrame)
        file_table_scroll.setStyleSheet(STYLE_SCROLL)
        file_table_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        file_table_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        file_table_scroll.setFixedHeight(1)   # re-sized to content in _refresh_file_list
        file_table_scroll.setWidget(self._file_table_w)
        file_table_scroll.installEventFilter(self)
        self._file_table_scroll = file_table_scroll
        body.addWidget(file_table_scroll)

        refresh_btn = QPushButton("Refresh file list")
        refresh_btn.setStyleSheet(STYLE_BTN_SMALL_GHOST)
        refresh_btn.setToolTip(
            "Re-scan constant/ for new STL/OBJ files.\n"
            "The list also refreshes on its own when you add or\n"
            "remove files. Your existing row settings are kept.")
        refresh_btn.clicked.connect(self._refresh_file_list)
        body.addWidget(refresh_btn, alignment=Qt.AlignLeft)

        shapes_row = QHBoxLayout()
        shapes_lbl = QLabel("Additional standard shapes:")
        shapes_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px; background: transparent;")
        self._num_shapes_sp = PlusMinusSpinBox()
        self._num_shapes_sp.setRange(0, 20)
        self._num_shapes_sp.setFixedWidth(70)
        self._num_shapes_sp.setToolTip(
            "Add a shape (Box / Sphere / Cylinder) to refine a\n"
            "region of space. No wall patch — refinement only.")
        self._num_shapes_sp.valueChanged.connect(self._refresh_shape_fields)
        shapes_row.addWidget(shapes_lbl)
        shapes_row.addWidget(self._num_shapes_sp)
        shapes_row.addStretch()
        body.addLayout(shapes_row)

        self._shapes_container_w = QWidget()
        self._shapes_container_w.setStyleSheet(f"background: {BG_CARD};")
        self._shapes_container_layout = QVBoxLayout(self._shapes_container_w)
        self._shapes_container_layout.setContentsMargins(0, 0, 0, 0)
        body.addWidget(self._shapes_container_w)

        # First build — no prior values to preserve, so skip the snapshot/banner.
        self._refresh_file_list(_preserve=False)

    def _browse_stl_into_case(self):
        """Copy chosen STL/OBJ files into constant/triSurface/ then refresh the table."""
        paths = pick_open_files(
            self, "Select STL/OBJ files", os.path.expanduser("~"),
            "Geometry files (*.stl *.obj);;All files (*.*)")
        if not paths:
            return
        tri_dir = os.path.join(self._cwd, "constant", "triSurface")
        os.makedirs(tri_dir, exist_ok=True)
        for p in paths:
            p = to_wsl_path(p)
            if os.path.isfile(p):
                shutil.copy2(p, os.path.join(tri_dir, os.path.basename(p)))
        self._refresh_file_list(_preserve=True)

    def _refresh_file_list(self, _preserve: bool = True):
        """Rebuild the Section 01 file table by re-scanning constant/ for
        STL/OBJ files. With _preserve=True (default) the user's per-row
        settings are snapshotted first and restored after the rebuild."""
        # Snapshot existing per-row values BEFORE destroying widgets so the user's
        # Surface Type / refinement / Vol Dir choices survive a refresh.  Without
        # this, every call rebuilt widgets at defaults — silently wiping Vol Dir
        # before Generate ran, which is what caused refinementRegions to come out
        # empty even after the backend fix.
        saved: dict = {}
        if _preserve:
            for fname, _full_path, w in self._file_rows:
                saved[fname] = {
                    "surf_type": w["surf_type_combo"].currentText(),
                    "cell_zone": w["cell_zone_cb"].isChecked(),
                    "surf_min":  w["surf_min_sp"].value(),
                    "surf_max":  w["surf_max_sp"].value(),
                    "vol_dir":   w["vol_dir_combo"].currentText(),
                    "vol_level": w["vol_level_sp"].value(),
                    "use":       w["use_cb"].isChecked(),
                }

        while self._file_table_layout.count():
            item = self._file_table_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._file_rows.clear()

        # Deferred so it runs after this call's layout changes settle, no
        # matter which return path below fires.
        QTimer.singleShot(0, self._resize_file_table_scroll)

        constant_dir = os.path.join(self._cwd, "constant")
        if not os.path.isdir(constant_dir):
            lbl = QLabel(f"  Not found: {constant_dir}")
            lbl.setStyleSheet(f"color: {KS_RED}; font-size: 14px; background: transparent;")
            self._file_table_layout.addWidget(lbl)
            return

        # Collect filenames and paths
        file_paths: dict[str, str] = {}
        for root, _, fnames in os.walk(constant_dir):
            for fn in fnames:
                if os.path.splitext(fn)[1].lower() in (".stl", ".obj"):
                    if fn not in file_paths:
                        file_paths[fn] = os.path.join(root, fn)

        files = sorted(file_paths.keys())
        if not files:
            empty_w = QWidget()
            empty_w.setStyleSheet(f"background: {BG_CARD};")
            empty_v = QVBoxLayout(empty_w)
            empty_v.setContentsMargins(0, 4, 0, 4)
            empty_v.setSpacing(8)
            lbl = QLabel("  No .stl/.obj files found under constant/")
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px; background: transparent;")
            empty_v.addWidget(lbl)
            browse_btn = QPushButton("Browse for STL/OBJ files…")
            browse_btn.setStyleSheet(STYLE_BTN_SMALL_RED)
            browse_btn.setToolTip("Copy geometry files into constant/triSurface/ for this case.")
            browse_btn.clicked.connect(self._browse_stl_into_case)
            empty_v.addWidget(browse_btn, alignment=Qt.AlignLeft)
            self._file_table_layout.addWidget(empty_w)
            return

        # Smart defaults: the largest STL (bounding-box volume) is assumed to
        # be the outer shell → Boundary; every other file is assumed to be a
        # solid body inside the domain → FaceZone + Cell Zone + Vol Inside, so
        # its cells are kept and named instead of silently discarded.
        # Preserved user values always win — the guess only fills new rows.
        outer_fname = None
        best_vol = 0.0
        for fn in files:
            fp = file_paths[fn]
            if fp not in self._stl_vol_cache:
                self._stl_vol_cache[fp] = (
                    self._stl_bbox_volume(fp) if fn.lower().endswith(".stl") else 0.0)
            if self._stl_vol_cache[fp] > best_vol:
                best_vol = self._stl_vol_cache[fp]
                outer_fname = fn
        if outer_fname is None:
            outer_fname = files[0]   # nothing parseable (binary STLs) — assume first

        # Header row
        hdr = QWidget()
        hdr.setStyleSheet("background: #EEF2F8;")
        hdr_row = QHBoxLayout(hdr)
        hdr_row.setContentsMargins(10, 6, 10, 6)
        hdr_row.setSpacing(4)

        def _hdr(text, w=None, tip=None):
            # Column header = plain text cell; the whole cell carries the
            # tooltip (per-column ⓘ badges made the header row too busy).
            # The cell has a solid background + STYLE_TOOLTIP appended, so the
            # transparent-owner tooltip leak does not apply.
            cell = QWidget()
            cell.setStyleSheet("background: #EEF2F8;" + STYLE_TOOLTIP)
            if tip:
                cell.setToolTip(tip)
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(3)
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"color: {KS_RED}; font-size: 11px; font-weight: 700;"
                " letter-spacing: 0.4px; background: transparent;")
            if w:
                cell.setFixedWidth(w)
                cl.setAlignment(Qt.AlignCenter)
                cl.addWidget(lbl)
            else:
                cell.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                cl.addWidget(lbl)
                cl.addStretch()
            return cell

        hdr_row.addWidget(_hdr("USE", 44, tip=(
            "Untick to exclude this file from meshing entirely —\n"
            "it stays on disk under constant/ but is left out of\n"
            "snappyHexMeshDict.")))
        hdr_row.addWidget(_hdr("FILE", tip=(
            "STL/OBJ files found under constant/.\n"
            "One file = one surface.")))
        hdr_row.addWidget(_hdr("SURFACE TYPE", 132, tip=(
            "How each surface is meshed:\n"
            "None     = no patch, refinement only\n"
            "Boundary = outer shell, mesh stops here\n"
            "FaceZone = solid body inside — tick Cell Zone to keep it")))
        hdr_row.addWidget(_hdr("CELL ZONE", 104, tip=(
            "Keeps + names the cells inside a FaceZone part so it\n"
            "shows in ParaView. Active only on FaceZone rows.")))
        hdr_row.addWidget(_hdr("MIN", 80, tip=(
            "Surface minimum refinement level.\n"
            "Level 0 = background size; each level halves it.\n"
            "Same value in MIN and MAX (e.g. 2,2) = uniform refinement —\n"
            "the usual choice for heat-simulation cases.")))
        hdr_row.addWidget(_hdr("MAX", 80, tip=(
            "Surface maximum refinement level.\n"
            "Use the same value as MIN for uniform refinement.\n"
            "Different values (e.g. 1,3) only when you want finer\n"
            "cells at surface edges and coarser away from them.")))
        hdr_row.addWidget(_hdr("VOL DIR", 112, tip=(
            "Where to add finer cells:\n"
            "None    = no volume refinement\n"
            "Inside  = inside this surface\n"
            "Outside = outside it (rare)")))
        hdr_row.addWidget(_hdr("V.LVL", 80, tip=(
            "How fine the volume refinement is when VOL DIR\n"
            "is Inside/Outside. Independent of MIN/MAX.\n"
            "Ignored when VOL DIR = None.")))
        self._file_table_layout.addWidget(hdr)

        for i, fname in enumerate(files):
            row_bg = BG_CARD if i % 2 == 0 else "#F8FAFC"
            row_w = QWidget()
            row_w.setStyleSheet(f"background: {row_bg};")
            row_layout = QHBoxLayout(row_w)
            row_layout.setContentsMargins(10, 4, 10, 4)
            row_layout.setSpacing(4)

            use_wrapper = QWidget()
            use_wrapper.setFixedWidth(44)
            use_wrapper.setStyleSheet(f"background: {row_bg};")
            use_wlayout = QHBoxLayout(use_wrapper)
            use_wlayout.setContentsMargins(0, 0, 0, 0)
            use_wlayout.setAlignment(Qt.AlignCenter)
            use_cb = QCheckBox()
            use_cb.setStyleSheet(STYLE_CHECKBOX)
            use_cb.setChecked(True)
            use_cb.setToolTip(
                "Untick to exclude this file from meshing entirely —\n"
                "it stays on disk under constant/ but is left out of\n"
                "snappyHexMeshDict.")
            use_wlayout.addWidget(use_cb)
            row_layout.addWidget(use_wrapper)

            name_lbl = QLabel(fname)
            name_lbl.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-family: {FONT_MONO}; font-size: 13px;"
                " background: transparent;")
            name_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            row_layout.addWidget(name_lbl)

            surf_type_combo = ChevronComboBox()
            surf_type_combo.addItems(_SURF_TYPES)
            surf_type_combo.setToolTip(
                "None     — no patch, refinement only\n"
                "Boundary — outer box / wall, mesh stops here\n"
                "FaceZone — solid part inside (cylinder, chip…).\n"
                "           Tick Cell Zone or the part's cells are\n"
                "           thrown away and it looks invisible.")
            surf_type_combo.setStyleSheet(STYLE_COMBO)
            surf_type_combo.setFixedWidth(132)
            row_layout.addWidget(surf_type_combo)

            cz_wrapper = QWidget()
            cz_wrapper.setFixedWidth(104)
            cz_wrapper.setStyleSheet(f"background: {row_bg};")
            cz_wlayout = QHBoxLayout(cz_wrapper)
            cz_wlayout.setContentsMargins(0, 0, 0, 0)
            cz_wlayout.setAlignment(Qt.AlignCenter)
            cell_zone_cb = QCheckBox()
            cell_zone_cb.setStyleSheet(STYLE_CHECKBOX)
            cell_zone_cb.setEnabled(False)
            cell_zone_cb.setToolTip(
                "Active only when Surface Type = FaceZone.\n"
                "Keeps + names the cells inside the part so it\n"
                "shows in ParaView. Required for solid bodies —\n"
                "unticked, the part disappears from the mesh.")
            cz_wlayout.addWidget(cell_zone_cb)
            row_layout.addWidget(cz_wrapper)

            surf_min_sp = PlusMinusSpinBox()
            surf_min_sp.setRange(0, 20)
            surf_min_sp.setValue(0)
            surf_min_sp.setFixedWidth(80)
            surf_min_sp.setToolTip(
                "Surface minimum refinement level.\n"
                "Level 0 = background size; each level halves it.")
            row_layout.addWidget(surf_min_sp)

            surf_max_sp = PlusMinusSpinBox()
            surf_max_sp.setRange(0, 20)
            surf_max_sp.setValue(0)
            surf_max_sp.setFixedWidth(80)
            surf_max_sp.setToolTip(
                "Surface maximum refinement level.\n"
                "Use the same value as MIN for uniform refinement.")
            row_layout.addWidget(surf_max_sp)

            vol_dir_combo = ChevronComboBox()
            vol_dir_combo.addItems(_VOL_DIRS)
            vol_dir_combo.setStyleSheet(STYLE_COMBO)
            vol_dir_combo.setFixedWidth(112)
            vol_dir_combo.setToolTip(
                "None    — no volume refinement (outer box)\n"
                "Inside  — refine cells inside (solid bodies).\n"
                "          V.Lvl sets how fine.\n"
                "Outside — refine cells outside (rare). Never\n"
                "          on the outer box.")
            row_layout.addWidget(vol_dir_combo)

            vol_level_sp = PlusMinusSpinBox()
            vol_level_sp.setRange(0, 20)
            vol_level_sp.setValue(0)
            vol_level_sp.setFixedWidth(80)
            vol_level_sp.setEnabled(False)   # enabled only when vol dir is not "None"
            vol_level_sp.setToolTip(
                "How fine the volume refinement is.\n"
                "Active only when Vol Dir is not None.\n"
                "Independent of MIN/MAX — set freely.")
            row_layout.addWidget(vol_level_sp)

            self._file_table_layout.addWidget(row_w)

            # Default-argument capture (cb=cell_zone_cb, sp=vol_level_sp) binds
            # the current iteration's widget to the closure.  Without it every
            # lambda would share the last iteration's widget when invoked later.
            def _update_cz(text, cb=cell_zone_cb, vd=vol_dir_combo, sp=vol_level_sp):
                enabled = (text == "FaceZone")
                cb.setEnabled(enabled)
                if not enabled:
                    cb.setChecked(False)
                sp.setEnabled(vd.currentText().lower() != "none")

            def _update_vol_level(text, sp=vol_level_sp):
                sp.setEnabled(text.lower() != "none")

            def _update_use(checked, stc=surf_type_combo, mn=surf_min_sp, mx=surf_max_sp,
                             vd=vol_dir_combo, vl=vol_level_sp, cb=cell_zone_cb):
                stc.setEnabled(checked)
                mn.setEnabled(checked)
                mx.setEnabled(checked)
                vd.setEnabled(checked)
                if checked:
                    _update_cz(stc.currentText())
                else:
                    cb.setEnabled(False)
                    vl.setEnabled(False)

            widgets = {
                "use_cb":          use_cb,
                "surf_type_combo": surf_type_combo,
                "cell_zone_cb":    cell_zone_cb,
                "surf_min_sp":     surf_min_sp,
                "surf_max_sp":     surf_max_sp,
                "vol_dir_combo":   vol_dir_combo,
                "vol_level_sp":    vol_level_sp,
            }
            self._file_rows.append((fname, file_paths[fname], widgets))

            # Restore preserved values BEFORE connecting signals so setCurrentIndex
            # and setValue calls don't fire _refresh_layer_patches mid-rebuild.
            if fname in saved:
                s = saved[fname]
                idx = surf_type_combo.findText(s["surf_type"])
                if idx >= 0:
                    surf_type_combo.setCurrentIndex(idx)
                cell_zone_cb.setChecked(s["cell_zone"])
                surf_min_sp.setValue(s["surf_min"])
                surf_max_sp.setValue(s["surf_max"])
                idx2 = vol_dir_combo.findText(s["vol_dir"])
                if idx2 >= 0:
                    vol_dir_combo.setCurrentIndex(idx2)
                # vol_level enable state is driven by vol_dir — set explicitly
                # since setCurrentIndex may not emit currentTextChanged when the
                # restored value happens to match the combo's existing index.
                vol_level_sp.setEnabled(s["vol_dir"].lower() != "none")
                vol_level_sp.setValue(s["vol_level"])
                use_cb.setChecked(s.get("use", True))
                _update_cz(s["surf_type"])
            elif fname == outer_fname:
                # Smart default (new row): outer shell — mesh stops here.
                surf_type_combo.setCurrentIndex(surf_type_combo.findText("Boundary"))
            else:
                # Smart default (new row): solid body inside the domain —
                # keep and name the cells inside, refine inside it so small
                # parts are captured by the mesh.
                surf_type_combo.setCurrentIndex(surf_type_combo.findText("FaceZone"))
                cell_zone_cb.setEnabled(True)
                cell_zone_cb.setChecked(True)
                vol_dir_combo.setCurrentIndex(vol_dir_combo.findText("Inside"))
                vol_level_sp.setEnabled(True)

            # Apply the surface-type gating once for every row (saved, outer
            # shell, or inner body) so Cell Zone starts enabled only on
            # FaceZone rows.
            _update_cz(surf_type_combo.currentText())
            _update_use(use_cb.isChecked())

            surf_type_combo.currentTextChanged.connect(_update_cz)
            surf_type_combo.currentTextChanged.connect(self._refresh_layer_patches)
            surf_type_combo.currentTextChanged.connect(lambda *_: self._refresh_preflight())
            vol_dir_combo.currentTextChanged.connect(_update_vol_level)
            use_cb.toggled.connect(_update_use)
            use_cb.toggled.connect(self._refresh_layer_patches)
            use_cb.toggled.connect(lambda *_: self._refresh_preflight())
            cell_zone_cb.toggled.connect(lambda *_: self._refresh_preflight())

        self._refresh_layer_patches()
        self._refresh_preflight()

        # Confirmation banner — only shown when values were actually preserved
        # (i.e. _preserve=True and there were saved rows from the previous build).
        if _preserve and saved:
            banner = QLabel(
                "✓ File list refreshed — your previous settings have been restored.")
            banner.setStyleSheet(
                "color: #166534; background: #DCFCE7;"
                " border: 1px solid #86EFAC; border-radius: 3px;"
                " padding: 4px 10px; font-size: 12px;")
            self._file_table_layout.addWidget(banner)
            QTimer.singleShot(4000, lambda: banner.setVisible(False))

    # ── Standard shapes ────────────────────────────────────────────────────────────

    def _refresh_shape_fields(self):
        """Rebuild the standard-shape sub-cards to match the requested count
        (the number picker next to "Additional standard shapes")."""
        while self._shapes_container_layout.count():
            item = self._shapes_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._shape_widgets.clear()

        n = self._num_shapes_sp.value()
        for i in range(n):
            sub = self._sub_card(self._shapes_container_layout, f"Shape {i + 1}")

            type_row = QHBoxLayout()
            type_lbl = QLabel("Type:")
            type_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;")
            type_lbl.setFixedWidth(140)
            type_combo = ChevronComboBox()
            type_combo.addItems(["Box", "Sphere", "Cylinder"])
            type_combo.setStyleSheet(STYLE_COMBO)
            type_combo.setFixedWidth(150)
            type_combo.setToolTip("Shape of the refinement region.")
            type_row.addWidget(type_lbl)
            type_row.addWidget(type_combo)
            type_row.addStretch()
            sub.addLayout(type_row)

            fields_w = QWidget()
            fields_w.setStyleSheet(f"background: {BG_CARD};")
            fields_layout = QVBoxLayout(fields_w)
            fields_layout.setContentsMargins(0, 0, 0, 0)
            fields_layout.setSpacing(4)
            sub.addWidget(fields_w)

            # Vol direction + level for shapes
            vol_row = QHBoxLayout()
            vol_dir_lbl = QLabel("Vol Direction:")
            vol_dir_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;")
            vol_dir_lbl.setFixedWidth(140)
            vol_dir_combo = ChevronComboBox()
            vol_dir_combo.addItems(_VOL_DIRS)
            vol_dir_combo.setStyleSheet(STYLE_COMBO)
            vol_dir_combo.setFixedWidth(94)
            vol_dir_combo.setToolTip(
                "Where this shape adds finer cells:\n"
                "Inside = within the shape (usual choice).")
            vol_level_sp = PlusMinusSpinBox()
            vol_level_sp.setRange(0, 20)
            vol_level_sp.setValue(0)
            vol_level_sp.setFixedWidth(60)
            vol_level_sp.setEnabled(False)
            vol_level_sp.setToolTip("How fine the refinement is. Active when Vol Dir is not None.")
            vol_row.addWidget(vol_dir_lbl)
            vol_row.addWidget(vol_dir_combo)
            vol_row.addSpacing(8)
            vol_row.addWidget(QLabel("V.Lvl:"))
            vol_row.addWidget(vol_level_sp)
            vol_row.addStretch()
            sub.addLayout(vol_row)

            sd = {
                "type_combo":    type_combo,
                "fields_layout": fields_layout,
                "widgets":       {},
                "vol_dir_combo": vol_dir_combo,
                "vol_level_sp":  vol_level_sp,
            }
            self._shape_widgets.append(sd)

            type_combo.currentTextChanged.connect(lambda _, d=sd: self._rebuild_shape_fields(d))
            vol_dir_combo.currentTextChanged.connect(
                lambda text, sp=vol_level_sp: sp.setEnabled(text.lower() != "none"))

            self._rebuild_shape_fields(sd)

    def _rebuild_shape_fields(self, sd: dict):
        """Swap a shape sub-card's coordinate fields to match its type: Box =
        min/max points, Sphere = centre + radius, Cylinder = two axis points +
        radius."""
        fl = sd["fields_layout"]
        while fl.count():
            item = fl.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        sd["widgets"].clear()

        t = sd["type_combo"].currentText()
        w = sd["widgets"]

        def xyz_row(label):
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;")
            lbl.setFixedWidth(140)
            vx, vy, vz = QLineEdit(), QLineEdit(), QLineEdit()
            for ed, ph in [(vx, "x"), (vy, "y"), (vz, "z")]:
                ed.setPlaceholderText(ph)
                ed.setStyleSheet(STYLE_ENTRY)
                ed.setFixedWidth(80)
            row.addWidget(lbl)
            row.addWidget(vx); row.addWidget(vy); row.addWidget(vz)
            row.addStretch()
            fl.addLayout(row)
            return vx, vy, vz

        def scalar_row(label):
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;")
            lbl.setFixedWidth(140)
            ed = QLineEdit()
            ed.setStyleSheet(STYLE_ENTRY)
            ed.setFixedWidth(100)
            row.addWidget(lbl); row.addWidget(ed); row.addStretch()
            fl.addLayout(row)
            return ed

        if t == "Box":
            w["min_x"], w["min_y"], w["min_z"] = xyz_row("Min point:")
            w["max_x"], w["max_y"], w["max_z"] = xyz_row("Max point:")
        elif t == "Sphere":
            w["cx"], w["cy"], w["cz"] = xyz_row("Centre:")
            w["radius"] = scalar_row("Radius:")
        elif t == "Cylinder":
            w["p1_x"], w["p1_y"], w["p1_z"] = xyz_row("Point 1 (axis start):")
            w["p2_x"], w["p2_y"], w["p2_z"] = xyz_row("Point 2 (axis end):")
            w["radius"] = scalar_row("Radius:")

    def _collect_shapes(self) -> list:
        """Read every shape sub-card into the backend's standard_shapes schema.
        Raises ValueError naming the shape when a coordinate is missing or not
        a number."""
        shapes = []
        for i, sd in enumerate(self._shape_widgets):
            t  = sd["type_combo"].currentText()
            sw = sd["widgets"]
            vol_dir = sd["vol_dir_combo"].currentText().lower()
            vol_lvl = sd["vol_level_sp"].value()
            try:
                if t == "Box":
                    params = {
                        "min": [float(sw["min_x"].text()), float(sw["min_y"].text()), float(sw["min_z"].text())],
                        "max": [float(sw["max_x"].text()), float(sw["max_y"].text()), float(sw["max_z"].text())],
                    }
                    stype = "searchableBox"
                elif t == "Sphere":
                    params = {
                        "centre": [float(sw["cx"].text()), float(sw["cy"].text()), float(sw["cz"].text())],
                        "radius": float(sw["radius"].text()),
                    }
                    stype = "searchableSphere"
                elif t == "Cylinder":
                    params = {
                        "point1": [float(sw["p1_x"].text()), float(sw["p1_y"].text()), float(sw["p1_z"].text())],
                        "point2": [float(sw["p2_x"].text()), float(sw["p2_y"].text()), float(sw["p2_z"].text())],
                        "radius": float(sw["radius"].text()),
                    }
                    stype = "searchableCylinder"
                else:
                    raise ValueError(f"Unknown shape type: {t}")
            except (ValueError, KeyError):
                raise ValueError(f"Shape {i + 1} ({t}): invalid or missing coordinate fields")
            shapes.append({
                "name":          f"shape_{i + 1}",
                "type":          stype,
                "params":        params,
                "vol_direction": vol_dir,
                "vol_level":     vol_lvl,
            })
        return shapes

    # ── Section 2: Castellation ────────────────────────────────────────────────────

    def _build_sec2(self):
        """Section 02 — Castellation: geometry unit, nCellsBetweenLevels, and
        the locationInMesh x/y/z pickers with the Suggest-point helper."""
        card, body = build_card("02", "Castellation", tip=(
            "First mesh stage: cut the background box around the\n"
            "shapes. Set cell transition and the inside point that\n"
            "tells the mesher which region to keep."))
        self._content_layout.addWidget(card)

        unit_row = QHBoxLayout()
        unit_lbl = QLabel("Geometry unit:")
        unit_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px; background: transparent;")
        unit_lbl.setFixedWidth(200)
        self._geom_unit_combo = ChevronComboBox()
        self._geom_unit_combo.addItems(_GEOM_UNITS)
        self._geom_unit_combo.setStyleSheet(STYLE_COMBO)
        self._geom_unit_combo.setFixedWidth(90)
        self._geom_unit_combo.setToolTip(
            "Unit your STL was exported in (OpenFOAM works in m).\n"
            "Most CAD = mm; large domains = m.")
        unit_row.addWidget(unit_lbl)
        unit_row.addWidget(self._geom_unit_combo)
        unit_row.addStretch()
        body.addLayout(unit_row)

        ncbl_row = QHBoxLayout()
        ncbl_lbl = QLabel("nCellsBetweenLevels:")
        ncbl_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px; background: transparent;")
        ncbl_lbl.setFixedWidth(200)
        self._ncbl_sp = PlusMinusSpinBox()
        self._ncbl_sp.setRange(1, 5)
        self._ncbl_sp.setValue(2)
        self._ncbl_sp.setFixedWidth(70)
        self._ncbl_sp.setToolTip(
            "Cells between each refinement level.\n"
            "Higher = smoother transition, more cells.\n"
            "Use 2 (default), 3 for layer prep.")
        ncbl_row.addWidget(ncbl_lbl)
        ncbl_row.addWidget(self._ncbl_sp)
        ncbl_row.addStretch()
        body.addLayout(ncbl_row)

        body.addWidget(self._label_small("LOCATION IN MESH  (x, y, z)"))
        loc_row = QHBoxLayout()
        self._loc_x_sp = self._make_coord_spinbox()
        self._loc_x_sp.setValue(0.000)
        self._loc_y_sp = self._make_coord_spinbox()
        self._loc_y_sp.setValue(0.000)
        self._loc_z_sp = self._make_coord_spinbox()
        self._loc_z_sp.setValue(0.000)
        for sp, ph in [(self._loc_x_sp, "x"), (self._loc_y_sp, "y"), (self._loc_z_sp, "z")]:
            sp.setPrefix(f"{ph}: ")
        for sp in [self._loc_x_sp, self._loc_y_sp, self._loc_z_sp]:
            sp.valueChanged.connect(lambda *_: self._refresh_preflight())
        for sp in [self._loc_x_sp, self._loc_y_sp, self._loc_z_sp]:
            sp.setToolTip(
                "A point in the fluid. Snappy keeps cells reachable\n"
                "from here, discards the rest. Must be:\n"
                "• inside the outer box\n"
                "• outside all solid bodies\n"
                "• not on a face or edge\n"
                "Wrong point = empty or broken mesh.")
        # Each PlusMinusSpinBox already draws its own rounded outline (#pmsp);
        # a visible gap between them is all that's needed to tell x/y/z apart.
        # An extra wrapper frame just doubled the border and bloated the
        # padding, making these pickers look different from every other one.
        for sp in [self._loc_x_sp, self._loc_y_sp, self._loc_z_sp]:
            loc_row.addWidget(sp)
            loc_row.addSpacing(10)
        suggest_btn = QPushButton("Suggest point")
        suggest_btn.setStyleSheet(STYLE_BTN_SMALL_GHOST)
        suggest_btn.setToolTip(
            "Auto-fills the point from the largest boundary STL\n"
            "(60% toward its corner). Always double-check it lands\n"
            "in fluid, outside every solid.")
        suggest_btn.clicked.connect(self._suggest_location_in_mesh)
        loc_row.addWidget(suggest_btn)
        loc_row.addStretch()
        body.addLayout(loc_row)

        self._location_warn = QLabel(
            "⚠ REQUIRED: Point must be inside the fluid domain — not on a face, edge, or inside a solid.\n"
            "Internal flow (fluid inside a box with objects): point must be inside the box "
            "AND outside all solid objects.\n"
            "External flow (fluid outside geometry): use a far-field point away from the body.\n"
            "Click ‘Suggest point’ to auto-fill from blockMeshDict — then sanity-check it against "
            "your STL bounds.")
        self._location_warn.setObjectName("location_warn")
        self._location_warn.setStyleSheet("""
            QLabel#location_warn {
                color: #991B1B;
                background: #FEE2E2;
                border: 1px solid #FECACA;
                border-radius: 3px;
                padding: 6px 10px;
                font-size: 12px;
            }
        """)
        self._location_warn.setWordWrap(True)
        body.addWidget(self._location_warn)

    # ── Section 3: Snap controls ───────────────────────────────────────────────────

    def _build_sec3(self):
        """Section 03 — Snap controls: informational only; implicit feature
        snapping is always on, so there is nothing to configure."""
        card, body = build_card("03", "Snap controls", tip=(
            "Second mesh stage: pull the cut cells onto the real\n"
            "surfaces so the mesh follows the shapes. Runs with\n"
            "built-in settings — nothing to set here."))
        self._content_layout.addWidget(card)

        body.addWidget(self._label_small("FEATURE EDGE CAPTURE"))
        note = QLabel(
            "Automatic (implicit) feature snapping is always on — sharp corners and "
            "edges are detected directly from the STL surfaces. No .eMesh files or "
            "surfaceFeatureExtract step needed.")
        note.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; background: transparent;")
        note.setWordWrap(True)
        body.addWidget(note)

    # ── Section 4: Layer addition ──────────────────────────────────────────────────

    def _build_sec4(self):
        """Section 04 — Layer addition: on/off checkbox plus a per-patch
        nSurfaceLayers list auto-populated from Section 01."""
        card, body = build_card("04", "Layer addition", tip=(
            "Third mesh stage: add thin flat cells on chosen walls\n"
            "for better near-wall detail. Turn on and set how many\n"
            "layers per patch, or leave off."))
        self._content_layout.addWidget(card)
        self._sec4_body = body

        self._add_layers_cb = QCheckBox("Add boundary layers?")
        self._add_layers_cb.setStyleSheet(STYLE_CHECKBOX)
        self._add_layers_cb.setToolTip(
            "Adds thin layers along walls for accurate heat\n"
            "and viscous flow. Get the base mesh right first.\n"
            "Slows meshing down noticeably.")
        self._add_layers_cb.toggled.connect(self._toggle_layer_details)
        body.addWidget(self._add_layers_cb)

        self._layer_details_w = QWidget()
        self._layer_details_w.setStyleSheet(f"background: {BG_CARD};")
        self._layer_details_layout = QVBoxLayout(self._layer_details_w)
        self._layer_details_layout.setContentsMargins(0, 6, 0, 0)
        self._layer_details_layout.setSpacing(4)
        body.addWidget(self._layer_details_w)
        self._layer_details_w.setVisible(False)

    def _toggle_layer_details(self, checked: bool):
        """Show/hide the per-patch layer list when the checkbox flips."""
        if self._layer_details_w:
            self._layer_details_w.setVisible(checked)
        if checked:
            self._refresh_layer_patches()
        self._update_dict_banner()

    def _refresh_layer_patches(self):
        """Rebuild the Section 04 patch list from the used Section 01 rows.
        Patch names follow the backend's rule: the STL solid name when the file
        has one named solid, every zone name for multi-zone files, otherwise
        the filename stem."""
        if not self._layer_details_layout:
            return

        while self._layer_details_layout.count():
            item = self._layer_details_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._layer_patch_widgets.clear()

        patches: list[str] = []
        for fname, full_path, widgets in self._file_rows:
            if not widgets["use_cb"].isChecked():
                continue
            surf_type = widgets["surf_type_combo"].currentText()
            if surf_type == "None":
                continue

            stem = os.path.splitext(fname)[0]
            if fname.lower().endswith(".stl") and os.path.isfile(full_path):
                if full_path not in self._zone_name_cache:
                    self._zone_name_cache[full_path] = get_stl_zone_names(full_path)
                zones = self._zone_name_cache[full_path]
                if len(zones) > 1:
                    patches.extend(zones)
                    continue
                # Single named solid (e.g. `solid external-walls`) — OpenFOAM names
                # the patch after the solid, not the filename, so mirror the
                # backend's _mesh_name_for_stl rule here.
                if len(zones) == 1 and zones[0] != "Unnamed":
                    patches.append(zones[0])
                    continue

            patches.append(stem)

        if not patches:
            lbl = QLabel("  (No surfaces with a non-None Surface Type in Section 01)")
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; background: transparent;")
            self._layer_details_layout.addWidget(lbl)
            return

        hdr = QLabel("Patch name  /  nSurfaceLayers:")
        hdr.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; background: transparent;")
        self._layer_details_layout.addWidget(hdr)

        for patch in patches:
            row = QHBoxLayout()
            lbl = QLabel(patch)
            lbl.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-family: {FONT_MONO}; font-size: 13px;"
                " background: transparent;")
            lbl.setFixedWidth(260)
            sp = PlusMinusSpinBox()
            sp.setRange(1, 10)
            sp.setValue(3)
            sp.setFixedWidth(70)
            sp.setToolTip(
                f"Number of wall layers on '{patch}'.\n"
                "Typical 3–5. More = better near-wall detail,\n"
                "more cells.")
            row.addWidget(lbl)
            row.addWidget(sp)
            row.addStretch()
            self._layer_details_layout.addLayout(row)
            self._layer_patch_widgets[patch] = sp

    # ── Section 5: Generate & Run ──────────────────────────────────────────────────

    def _build_sec5(self):
        """Section 05 — Generate & Run: pre-flight checklist, overwrite
        warning, auto-open-ParaView option, the run button, and the result
        banner."""
        card, body = build_card("05", "Generate & Run", tip=(
            "Writes the snappyHexMeshDict from the settings above\n"
            "and runs the mesher. Watch progress in the log drawer."))
        self._content_layout.addWidget(card)

        desc = QLabel(
            "Generates system/snappyHexMeshDict from a template (whole file in one pass), "
            "records your inputs to snappy_inputs.json, then runs snappyHexMesh -overwrite.")
        desc.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px; background: transparent;")
        desc.setWordWrap(True)
        body.addWidget(desc)

        if not _BACKEND_OK:
            err_lbl = QLabel(f"Backend unavailable: {_BACKEND_ERR}")
            err_lbl.setStyleSheet(
                "color: #B91C1C; font-size: 12px; background: #FEE2E2;"
                " border: 1px solid #FECACA; border-radius: 4px; padding: 6px 10px;")
            err_lbl.setWordWrap(True)
            body.addWidget(err_lbl)

        self._time_dirs_lbl = QLabel("No time directories found.")
        self._time_dirs_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 14px; background: transparent;")
        body.addWidget(self._time_dirs_lbl)

        body.addWidget(self._label_small("PRE-FLIGHT CHECK"))
        self._preflight_lbl = QLabel("")
        self._preflight_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-family: {FONT_MONO}; font-size: 12px;"
            " background: transparent;")
        self._preflight_lbl.setWordWrap(True)
        body.addWidget(self._preflight_lbl)

        sep = QFrame()
        sep.setObjectName("sec5_sep")
        sep.setFixedHeight(1)
        sep.setStyleSheet("QFrame#sec5_sep { background: #E5E7EB; }")
        body.addWidget(sep)

        self._dict_banner = QLabel("")
        self._dict_banner.setObjectName("dict_banner")
        self._dict_banner.setStyleSheet("""
            QLabel#dict_banner {
                background: #FFF8E1; color: #7A5C00;
                border: 1px solid #F0C040; border-radius: 4px;
                padding: 5px 10px; font-size: 12px;
            }
        """)
        self._dict_banner.setWordWrap(True)
        self._dict_banner.setVisible(False)
        body.addWidget(self._dict_banner)

        self._open_paraview_cb = QCheckBox("Open in ParaView automatically after successful mesh generation")
        self._open_paraview_cb.setStyleSheet(STYLE_CHECKBOX)
        self._open_paraview_cb.setToolTip(
            "Opens ParaView when meshing succeeds.\n"
            "ParaView must be installed on Windows.\n"
            "There: click Apply, then Read zones to see inner solids.")
        body.addWidget(self._open_paraview_cb)

        btn_row = QHBoxLayout()
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setStyleSheet(STYLE_BTN_SMALL_GHOST)
        self._cancel_btn.setEnabled(False)   # only meaningful while a run is active
        self._cancel_btn.setToolTip(
            "Stop the running mesher (Esc).\n"
            "A cancelled mesh is incomplete — run again before using it.")
        self._cancel_btn.clicked.connect(self.cancel_run)
        btn_row.addWidget(self._cancel_btn)
        self._run_btn = QPushButton("Generate Snappy Hex Mesh")
        self._run_btn.setStyleSheet(STYLE_BTN_PRIMARY)
        self._run_btn.setEnabled(_BACKEND_OK)
        self._run_btn.setToolTip(
            "Writes snappyHexMeshDict, then runs snappyHexMesh.\n"
            "Before running, check:\n"
            "✓ Background Mesh done (blockMesh ran)\n"
            "✓ Outer = Boundary; solids = FaceZone + Cell Zone\n"
            "✓ Solids have Vol Dir = Inside\n"
            "✓ Point is inside the box, outside solids, not (0,0,0)")
        self._run_btn.clicked.connect(self._generate_and_run)
        btn_row.addStretch()
        btn_row.addWidget(self._run_btn)
        body.addLayout(btn_row)

        # Result banner (red error+fix / green success) shown after a run.
        self._msg_banner = MessageBanner()
        body.addWidget(self._msg_banner)

        self._update_dict_banner()
        self._update_time_dirs()
        self._refresh_preflight()

    def _refresh_preflight(self):
        """Cheap pre-Generate sanity checks, rendered as a checklist in Sec 05."""
        if not self._preflight_lbl:
            return
        checks = []

        bg_mesh_ok = os.path.isfile(os.path.join(self._cwd, "constant", "polyMesh", "points"))
        checks.append((bg_mesh_ok, "Background mesh exists (blockMesh has run)"))

        used_rows = [w for _f, _p, w in self._file_rows if w["use_cb"].isChecked()]
        has_boundary = any(w["surf_type_combo"].currentText() == "Boundary" for w in used_rows)
        checks.append((has_boundary, "At least one file set to Boundary (outer shell)"))

        facezone_rows = [w for w in used_rows if w["surf_type_combo"].currentText() == "FaceZone"]
        facezone_no_cz = [w for w in facezone_rows if not w["cell_zone_cb"].isChecked()]
        checks.append((not facezone_no_cz,
                        "Every FaceZone file has Cell Zone ticked" if facezone_rows
                        else "Every FaceZone file has Cell Zone ticked (n/a — no FaceZone files)"))

        loc_set = not (self._loc_x_sp and self._loc_x_sp.value() == 0.0
                       and self._loc_y_sp and self._loc_y_sp.value() == 0.0
                       and self._loc_z_sp and self._loc_z_sp.value() == 0.0)
        checks.append((loc_set, "Location In Mesh set (not 0,0,0)"))

        lines = []
        for ok, text in checks:
            mark = "✓" if ok else "✗"
            color = "#166534" if ok else "#B91C1C"
            lines.append(f'<span style="color:{color};">{mark}</span> {text}')
        self._preflight_lbl.setText("<br>".join(lines))

    # ── Banner / status helpers ────────────────────────────────────────────────────

    def _scan_time_dirs(self) -> list:
        """Return a sorted list of non-zero numeric time directories in the case root."""
        try:
            dirs = []
            for e in os.listdir(self._cwd):
                if os.path.isdir(os.path.join(self._cwd, e)):
                    try:
                        if float(e) != 0.0:
                            dirs.append(e)
                    except ValueError:
                        pass
            return sorted(dirs, key=float)
        except Exception:
            return []

    def _update_time_dirs(self):
        """Refresh the Section 05 time-directory label from the current case root."""
        if not self._time_dirs_lbl:
            return
        dirs = self._scan_time_dirs()
        if dirs:
            self._time_dirs_lbl.setText("Existing time dirs: " + "  ".join(f"/{d}" for d in dirs))
        else:
            self._time_dirs_lbl.setText("No time directories found.")

    def _update_dict_banner(self):
        """Show a warning banner in Section 05 listing files that will be overwritten."""
        if not self._dict_banner:
            return
        will = []
        snappy = os.path.join(self._cwd, "system", "snappyHexMeshDict")
        if os.path.isfile(snappy):
            will.append("system/snappyHexMeshDict")
        if os.path.isfile(os.path.join(self._cwd, "snappy_inputs.json")):
            will.append("snappy_inputs.json")
        if will:
            self._dict_banner.setText("Will overwrite: " + ",  ".join(will))
            self._dict_banner.setVisible(True)
        else:
            self._dict_banner.setVisible(False)

    def set_case_dir(self, case_dir: str):
        """Called by MainWindow when the user picks a project on the landing page."""
        case_dir = to_wsl_path(case_dir)
        self._cwd = case_dir
        self._zone_name_cache.clear()   # new case may have different STL contents
        self._stl_vol_cache.clear()
        if self._cwd_lbl:
            self._cwd_lbl.setText(case_dir)
        self._refresh_file_list()
        self._update_dict_banner()
        self._update_time_dirs()
        self._rewatch_constant()

    def _change_cwd(self):
        """Change… button on the CWD bar: switch to another case folder,
        clear the per-case caches, and rebuild everything that depends on it.
        Warns (but does not block) when constant/ or system/ is missing."""
        d = pick_existing_dir(self, "Select OpenFOAM case directory", self._cwd)
        if not d:
            return
        d = to_wsl_path(d)
        self._cwd = d
        self._zone_name_cache.clear()
        self._stl_vol_cache.clear()
        self._cwd_lbl.setText(d)
        if not os.path.isdir(os.path.join(d, "constant")) or not os.path.isdir(os.path.join(d, "system")):
            msg_warning(
                self, "Possible invalid case root",
                "The selected directory does not contain both constant/ and system/.\n"
                "It may not be a valid OpenFOAM case root.")
        self._refresh_file_list()
        self._update_dict_banner()
        self._update_time_dirs()
        self._rewatch_constant()

    # ── Auto file-list refresh ─────────────────────────────────────────────────────

    def _rewatch_constant(self):
        """Point the file-system watcher at the current case's constant/ tree.
        QFileSystemWatcher is not recursive, so every subdirectory is added
        explicitly; a new subfolder is picked up when its parent fires."""
        old = self._fs_watcher.directories() + self._fs_watcher.files()
        if old:
            self._fs_watcher.removePaths(old)
        constant = os.path.join(self._cwd, "constant")
        if not os.path.isdir(constant):
            return
        dirs = [constant]
        for root, subdirs, _files in os.walk(constant):
            dirs.extend(os.path.join(root, d) for d in subdirs)
        self._fs_watcher.addPaths(dirs)

    def _on_constant_changed(self, _path: str):
        """A watched path changed — (re)start the debounce timer and make sure
        any newly created subfolders are watched too."""
        self._rewatch_constant()
        self._watch_debounce.start()

    def _auto_refresh_files(self):
        """Debounced rebuild after file changes. Preserves the user's per-row
        settings; new files get smart defaults, removed files drop out — no
        popup, matching the manual Refresh button."""
        self._refresh_file_list(_preserve=True)

    # ── LocationInMesh auto-suggest ────────────────────────────────────────────────

    def _suggest_location_in_mesh(self):
        """Read the largest boundary STL's bounding box; fall back to blockMeshDict on any error.

        Why STL-first: the background blockMesh is enlarged by ~10 % around the
        outer-domain STL, so a point at 60 % from the blockMesh centroid can land
        outside the actual STL box and produce an empty mesh.  Reading the STL
        directly anchors the suggested point inside the real domain.
        """
        green_style = """
            QLabel#location_warn {
                color: #166534; background: #DCFCE7;
                border: 1px solid #86EFAC; border-radius: 3px;
                padding: 6px 10px; font-size: 12px;
            }
        """

        # ── Try the largest boundary STL first ─────────────────────────────
        stl_bounds = None
        stl_name   = None
        try:
            vertex_re = _VERTEX_RE
            best_vol = 0.0
            for fname, full_path, widgets in self._file_rows:
                if widgets["surf_type_combo"].currentText() == "None":
                    continue
                if not fname.lower().endswith(".stl") or not os.path.isfile(full_path):
                    continue
                with open(full_path, "r", errors="ignore") as f:
                    text = f.read()
                verts = vertex_re.findall(text)
                if not verts:
                    continue
                xs = [float(v[0]) for v in verts]
                ys = [float(v[1]) for v in verts]
                zs = [float(v[2]) for v in verts]
                mn_x, mx_x = min(xs), max(xs)
                mn_y, mx_y = min(ys), max(ys)
                mn_z, mx_z = min(zs), max(zs)
                vol = (mx_x - mn_x) * (mx_y - mn_y) * (mx_z - mn_z)
                if vol > best_vol:
                    best_vol   = vol
                    stl_bounds = (mn_x, mx_x, mn_y, mx_y, mn_z, mx_z)
                    stl_name   = fname
        except Exception:
            stl_bounds = None

        if stl_bounds is not None:
            min_x, max_x, min_y, max_y, min_z, max_z = stl_bounds
            cx = (min_x + max_x) / 2
            cy = (min_y + max_y) / 2
            cz = (min_z + max_z) / 2
            px = round(cx + (max_x - cx) * 0.6, 6)
            py = round(cy + (max_y - cy) * 0.6, 6)
            pz = round(cz + (max_z - cz) * 0.6, 6)
            self._loc_x_sp.setValue(px)
            self._loc_y_sp.setValue(py)
            self._loc_z_sp.setValue(pz)
            if self._location_warn:
                self._location_warn.setText(
                    f"✓ Suggested point: ({px}, {py}, {pz})\n"
                    f"Domain reference: {stl_name} bounds "
                    f"({min_x:.4g} {min_y:.4g} {min_z:.4g}) → "
                    f"({max_x:.4g} {max_y:.4g} {max_z:.4g})\n"
                    "⚠ VERIFY this point is outside all inner solid bodies (cylinders, fins).\n"
                    "  If solids are centred at the origin, try moving X further toward the wall.")
                self._location_warn.setStyleSheet(green_style)
            return

        # ── Fallback: parse blockMeshDict vertices ─────────────────────────
        bmd_path = os.path.join(self._cwd, "system", "blockMeshDict")
        if not os.path.exists(bmd_path):
            if self._location_warn:
                self._location_warn.setText(
                    "⚠ blockMeshDict not found. Run the Background Mesh tab first.")
            return

        try:
            with open(bmd_path, "r") as f:
                content = f.read()

            # Scope the search to the vertices block to avoid matching cell-count
            # tuples in the blocks entry (e.g. "(22 22 22)") which inflate the bbox.
            verts_match = re.search(r'\bvertices\s*\((.*?)\);', content, re.DOTALL)
            search_text = verts_match.group(1) if verts_match else content

            vertices = re.findall(
                r"\(\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s+"
                r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s+"
                r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*\)",
                search_text)
            if not vertices:
                if self._location_warn:
                    self._location_warn.setText(
                        "⚠ Could not parse vertices from blockMeshDict.")
                return

            coords = [(float(x), float(y), float(z)) for x, y, z in vertices]
            min_x = min(c[0] for c in coords); max_x = max(c[0] for c in coords)
            min_y = min(c[1] for c in coords); max_y = max(c[1] for c in coords)
            min_z = min(c[2] for c in coords); max_z = max(c[2] for c in coords)
            cx = (min_x + max_x) / 2
            cy = (min_y + max_y) / 2
            cz = (min_z + max_z) / 2
            px = round(cx + (max_x - cx) * 0.6, 6)
            py = round(cy + (max_y - cy) * 0.6, 6)
            pz = round(cz + (max_z - cz) * 0.6, 6)

            self._loc_x_sp.setValue(px)
            self._loc_y_sp.setValue(py)
            self._loc_z_sp.setValue(pz)
            if self._location_warn:
                self._location_warn.setText(
                    f"✓ Point set: ({px}, {py}, {pz})  (from blockMeshDict — STL bounds unavailable)\n"
                    "Internal flow: point must be inside the box AND outside all solid objects.\n"
                    "External flow: point must be in the far-field region away from the body.")
                self._location_warn.setStyleSheet(green_style)

        except Exception as e:
            if self._location_warn:
                self._location_warn.setText(f"⚠ Parse error: {e}")

    # ── Collect data (GUI thread only) ─────────────────────────────────────────────

    def _collect_data(self) -> dict:
        """Build the config dict from widget values. Raises ValueError on invalid input."""
        files = []
        for fname, _full_path, widgets in self._file_rows:
            if not widgets["use_cb"].isChecked():
                continue
            surf_text = widgets["surf_type_combo"].currentText()
            vol_text  = widgets["vol_dir_combo"].currentText()
            surf_min  = widgets["surf_min_sp"].value()
            surf_max  = widgets["surf_max_sp"].value()
            if surf_max < surf_min:
                raise ValueError(
                    f"{fname}: MAX ({surf_max}) must be >= MIN ({surf_min}).")

            files.append({
                "filename":     fname,
                "surface_type": surf_text.lower(),
                "cell_zone":    widgets["cell_zone_cb"].isChecked(),
                "surface_min":  surf_min,
                "surface_max":  surf_max,
                "vol_direction": vol_text.lower(),
                "vol_level":    widgets["vol_level_sp"].value(),
            })

        shapes = self._collect_shapes()

        ncbl = self._ncbl_sp.value() if self._ncbl_sp else 2
        loc  = [
            self._loc_x_sp.value() if self._loc_x_sp else 0.0,
            self._loc_y_sp.value() if self._loc_y_sp else 0.0,
            self._loc_z_sp.value() if self._loc_z_sp else 0.0,
        ]
        if loc[0] == 0.0 and loc[1] == 0.0 and loc[2] == 0.0:
            raise ValueError(
                "locationInMesh is (0, 0, 0) — this will fail.\n"
                "Use the 'Suggest point' button or enter a point inside your fluid domain.")
        geom_unit    = self._geom_unit_combo.currentText() if self._geom_unit_combo else "m"
        implicit     = self._snap_implicit_cb.isChecked() if self._snap_implicit_cb else True
        add_layers   = self._add_layers_cb.isChecked() if self._add_layers_cb else False

        patches = []
        if add_layers:
            for name, sp in self._layer_patch_widgets.items():
                patches.append({"name": name, "nSurfaceLayers": sp.value()})

        return {
            "geometry": {
                "files":           files,
                "standard_shapes": shapes,
            },
            "castellated": {
                "geometry_unit":       geom_unit,
                "nCellsBetweenLevels": ncbl,
                "locationInMesh":      loc,
            },
            "snap": {
                "implicitFeatureSnap": implicit,
            },
            "layers": {
                "enabled": add_layers,
                "patches": patches,
            },
        }

    # ── Generate & Run ─────────────────────────────────────────────────────────────

    def _generate_and_run(self):
        """Run button: re-check pre-flight, collect the config on the GUI
        thread (popping a dialog on bad input), then hand it to _SnappyWorker
        so the mesher runs without freezing the window."""
        self._refresh_preflight()
        if not _BACKEND_OK:
            msg_critical(self, "Backend unavailable", _BACKEND_ERR)
            return

        try:
            config = self._collect_data()
        except ValueError as exc:
            msg_critical(self, "Invalid input", str(exc))
            return

        # Remember non-case-specific settings for the next app launch.
        save_prefs({
            "snappy_unit":       self._geom_unit_combo.currentText() if self._geom_unit_combo else "mm",
            "snappy_ncbl":       self._ncbl_sp.value() if self._ncbl_sp else 2,
            "snappy_add_layers": self._add_layers_cb.isChecked() if self._add_layers_cb else False,
        })

        self._run_btn.setEnabled(False)
        self._run_btn.setText("Running...")
        if self._cancel_btn:
            self._cancel_btn.setEnabled(True)
        self._log.set_running(True)
        self._log.write("\n[snappyHexMesh] Starting...\n", "info")

        # Reset per-run state for the result banner.
        self._run_log = []
        if self._msg_banner:
            self._msg_banner.hide_msg()
        self._log.set_step("Step 1/3: Castellating mesh…")

        worker = _SnappyWorker(config, self._cwd)
        worker.log_signal.connect(self._log.write)
        worker.log_signal.connect(self._collect_log)
        worker.finished_signal.connect(self._on_run_done)
        worker.start()
        self._run_worker = worker

    def is_meshing(self) -> bool:
        """True while a snappyHexMesh worker is running (used by the main
        window's close guard so the user cannot quit mid-run without
        confirming)."""
        worker = getattr(self, "_run_worker", None)
        return bool(worker and worker.isRunning())

    def cancel_run(self):
        """Stop a running snappyHexMesh worker (Cancel button / Esc shortcut).

        The mesher is killed mid-write, so any polyMesh it produced is
        incomplete — we warn instead of deleting (nothing destructive)."""
        worker = getattr(self, "_run_worker", None)
        if not (worker and worker.isRunning()):
            return
        worker.terminate()
        self._log.write("[snappyHexMesh] Cancelled by user.\n", "warn")
        self._log.set_running(False)
        self._log.set_step("")
        self._run_btn.setEnabled(True)
        self._run_btn.setText("Generate Dict && Run snappyHexMesh")
        if self._cancel_btn:
            self._cancel_btn.setEnabled(False)
        if self._msg_banner:
            self._msg_banner.show_error(
                "Run cancelled. The mesh is incomplete — run "
                "Generate again before using it.")
        self._log.status_changed.emit("Cancelled", "#F59E0B")

    def _collect_log(self, message: str, _tag: str = "info"):
        """Accumulate worker output so a failed run can be scanned for a plain fix,
        and update the Step X/3 label from snappyHexMesh's own phase headers."""
        self._run_log.append(message)
        low = message.lower()
        if "snapping mesh" in low:
            self._log.set_step("Step 2/3: Snapping mesh…")
        elif "adding layers" in low or "layer addition" in low:
            self._log.set_step("Step 3/3: Adding layers…")
        elif "castellating mesh" in low:
            self._log.set_step("Step 1/3: Castellating mesh…")

    def _on_run_done(self, success: bool):
        """Worker finished: reset the run button and status displays, show the
        green/red result banner, and optionally auto-launch ParaView."""
        self._log.set_running(False)
        self._log.set_step("")
        self._run_btn.setEnabled(True)
        self._run_btn.setText("Generate Dict && Run snappyHexMesh")
        if self._cancel_btn:
            self._cancel_btn.setEnabled(False)
        self._update_time_dirs()
        self._update_dict_banner()
        tag   = "info" if success else "error"
        color = "#22C55E" if success else "#EF4444"
        msg   = "Done" if success else "Error — check log"
        self._log.write(f"[snappyHexMesh] {msg}\n", tag)
        self._log.status_changed.emit(msg, color)

        if self._msg_banner:
            if success:
                self._msg_banner.show_success(
                    "Mesh generated. Open it in ParaView to check the result "
                    "(click Apply, then Read zones to see inner solids).")
            else:
                fix = scan_log_for_fix("".join(self._run_log))
                self._msg_banner.show_error(
                    fix or "Meshing failed. Open the log below and read the last "
                    "few red lines to see what went wrong.")
        # Auto-launch ParaView: both the executable and the .foam sentinel file
        # live on the Windows side, so WSL paths must be converted to Windows
        # UNC format via 'wslpath -w' before handing them to cmd.exe.
        if success and self._open_paraview_cb and self._open_paraview_cb.isChecked():
            pv_exe = find_paraview_exe()
            if pv_exe:
                case_name = os.path.basename(self._cwd)
                foam_file = os.path.join(self._cwd, f"{case_name}.foam")
                try:
                    pv_res   = subprocess.run(["wslpath", "-w", pv_exe],   capture_output=True, text=True)
                    foam_res = subprocess.run(["wslpath", "-w", foam_file], capture_output=True, text=True)
                    if pv_res.returncode == 0 and foam_res.returncode == 0:
                        subprocess.Popen(["cmd.exe", "/c", pv_res.stdout.strip(), foam_res.stdout.strip()])
                    else:
                        subprocess.Popen([pv_exe, foam_file])
                    self._log.write("[ParaView] Launching ParaView...", "info")
                except Exception as exc:
                    self._log.write(f"[ParaView] Launch failed: {exc}", "warn")
            else:
                self._log.write("[ParaView] Not found — install ParaView to use this feature.", "warn")
