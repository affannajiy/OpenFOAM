#!/usr/bin/env python3
"""
ui_snappy_hex.py — Tab 2: SnappyHexMesh Dict generator and mesh runner.

Overview
--------
Five-section scrollable card form.  Per-file surface/volume refinement is
configured directly in the Section 01 file table.  On "Generate
snappyHexMeshDict" the GUI builds a merged JSON config dict and hands it to
generate_snappy_dict_from_config() in setup_snappy.py, which renders a
Jinja2 template into system/snappyHexMeshDict.

Thread safety
-------------
All widget reads happen in _collect_data() on the GUI thread before any
worker is started.  Workers receive a plain Python dict — no Qt objects.

Section layout
--------------
  01 Geometry     — file table with per-row surface type / refinement / vol dir
                    + standard shapes (Box / Cylinder / Sphere)
  02 Castellation — geometry unit, nCellsBetweenLevels, locationInMesh
  03 Snap         — implicit/explicit feature snap toggle
  04 Layers       — per-patch nSurfaceLayers (populated from Section 01 choices)
  05 Generate     — Generate / Run buttons + overwrite banners
"""

import os
import sys
import json
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QScrollArea, QFrame, QFileDialog, QMessageBox, QComboBox,
    QCheckBox, QSizePolicy,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from ui_shared import (
    KS_RED, BG_APP, BG_CARD, BG_SUBTLE, BORDER, BORDER_SOFT,
    TEXT_PRIMARY, TEXT_MUTED, TEXT_WHITE,
    STYLE_BTN_PRIMARY, STYLE_BTN_SMALL_GHOST,
    STYLE_ENTRY, STYLE_COMBO, STYLE_SCROLL, STYLE_CHECKBOX,
    build_card, run_of_command, PlusMinusSpinBox,
)

try:
    from setup_snappy import generate_snappy_dict_from_config, deep_merge, _SETUP_OK, _SETUP_ERR
    _BACKEND_OK  = _SETUP_OK
    _BACKEND_ERR = _SETUP_ERR
except Exception as _imp_exc:
    _BACKEND_OK  = False
    _BACKEND_ERR = str(_imp_exc)
    def generate_snappy_dict_from_config(*a, **kw):
        raise RuntimeError(_BACKEND_ERR)
    def deep_merge(base, override):
        import copy
        result = copy.deepcopy(base)
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = deep_merge(result[k], v)
            else:
                result[k] = v
        return result

_DEFAULTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "defaults.json")
_GEOM_UNITS = ["mm", "m", "cm", "um", "in", "ft"]
_SURF_TYPES = ["None", "Boundary", "FaceZone", "FaceZone+CellZone"]
_VOL_DIRS   = ["None", "Inside", "Outside"]


def _load_defaults() -> dict:
    try:
        with open(_DEFAULTS_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


# ── Worker threads ──────────────────────────────────────────────────────────────

class _GenerateWorker(QThread):
    log_line       = pyqtSignal(str, str)
    status_changed = pyqtSignal(str, str)

    def __init__(self, config: dict, sys_dir: str, cwd: str):
        super().__init__()
        self.config  = config
        self.sys_dir = sys_dir
        self.cwd     = cwd

    def run(self):
        self.status_changed.emit("Running...", "#F59E0B")
        try:
            generate_snappy_dict_from_config(
                self.config, self.sys_dir, self.log_line.emit, self.cwd)
            self.log_line.emit("[snappyHexMeshDict] Done.\n", "info")
            self.status_changed.emit("Done", "#22C55E")
        except SystemExit as exc:
            msg = exc.args[0] if exc.args else str(exc)
            self.log_line.emit(f"[snappyHexMeshDict] Error: {msg}\n", "error")
            self.status_changed.emit("Error — check log", "#EF4444")
        except Exception as exc:
            self.log_line.emit(f"[snappyHexMeshDict] Error: {exc}\n", "error")
            self.status_changed.emit("Error — check log", "#EF4444")


class _RunSnappyWorker(QThread):
    log_line       = pyqtSignal(str, str)
    status_changed = pyqtSignal(str, str)

    def __init__(self, cwd: str):
        super().__init__()
        self.cwd = cwd

    def run(self):
        self.status_changed.emit("Running...", "#F59E0B")
        try:
            cwd = self.cwd
            for entry in os.listdir(cwd):
                entry_path = os.path.join(cwd, entry)
                if entry.isdigit() and os.path.isdir(entry_path):
                    try:
                        shutil.rmtree(entry_path)
                    except Exception:
                        pass

            rc = run_of_command("snappyHexMesh", cwd, self.log_line.emit)
            if rc == 0:
                case_name = os.path.basename(cwd)
                try:
                    for f in os.listdir(cwd):
                        if f.endswith(".foam"):
                            try:
                                os.remove(os.path.join(cwd, f))
                            except Exception:
                                pass
                    foam_path = os.path.join(cwd, f"{case_name}.foam")
                    open(foam_path, "w").close()
                    self.log_line.emit(f"[snappyHexMesh] .foam updated: {foam_path}\n", "info")
                except Exception as fe:
                    self.log_line.emit(f"[snappyHexMesh] Warning: .foam update failed: {fe}\n", "warn")
                self.log_line.emit("[snappyHexMesh] Done.\n", "info")
                self.status_changed.emit("Done", "#22C55E")
            else:
                self.log_line.emit(f"[snappyHexMesh] Exited with code {rc}\n", "error")
                self.status_changed.emit("Error — check log", "#EF4444")
        except Exception as exc:
            self.log_line.emit(f"[snappyHexMesh] Exception: {exc}\n", "error")
            self.status_changed.emit("Error — check log", "#EF4444")


# ── Tab widget ──────────────────────────────────────────────────────────────────

class SnappyHexWidget(QWidget):
    """Tab 2 widget — SnappyHexMesh Dict generator and mesh runner."""

    def __init__(self, log_drawer, parent=None):
        super().__init__(parent)
        self._log = log_drawer
        self._cwd = os.getcwd()

        # (fname, widgets_dict) — widgets_dict keys:
        #   surf_type_combo, surf_min_sp, surf_max_sp, vol_dir_combo, vol_level_sp
        self._file_rows: list     = []
        self._shape_widgets: list = []

        # stem → PlusMinusSpinBox (nSurfaceLayers)
        self._layer_patch_widgets: dict = {}

        # Static refs populated by _build_sec*
        self._cwd_lbl           = None
        self._file_table_layout = None
        self._sec1_err          = None
        self._num_shapes_sp     = None
        self._shapes_container_layout = None
        self._geom_unit_combo   = None
        self._ncbl_sp           = None
        self._loc_x_ed          = None
        self._loc_y_ed          = None
        self._loc_z_ed          = None
        self._snap_implicit_cb  = None
        self._add_layers_cb     = None
        self._layer_details_w   = None
        self._layer_details_layout = None
        self._gen_btn           = None
        self._run_btn           = None
        self._time_dirs_lbl     = None
        self._dict_banner       = None
        self._snappy_banner     = None

        self.setStyleSheet(f"background: {BG_APP};")
        self._build()

    # ── Layout ──────────────────────────────────────────────────────────────────

    def _build(self):
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
            f"color: {TEXT_MUTED}; font-family: Consolas; font-size: 11px; background: transparent;")
        self._cwd_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        change_btn = QPushButton("Change…")
        change_btn.setStyleSheet(STYLE_BTN_SMALL_GHOST)
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

    # ── Shared helpers ───────────────────────────────────────────────────────────

    def _label_small(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-family: 'Segoe UI'; font-size: 11px;"
            " font-weight: 600; letter-spacing: 0.4px; background: transparent;")
        return lbl

    def _sub_card(self, parent_layout: QVBoxLayout, title: str) -> QVBoxLayout:
        wrapper = QFrame()
        wrapper.setStyleSheet(f"""
            QFrame {{
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

    # ── Section 1: Geometry ──────────────────────────────────────────────────────

    def _build_sec1(self):
        card, body = build_card("01", "Geometry")
        self._content_layout.addWidget(card)
        self._sec1_body = body

        desc = QLabel(
            "Files found under constant/ — set Surface Type and Refinement levels for each:")
        desc.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px; background: transparent;")
        body.addWidget(desc)

        self._file_table_w = QWidget()
        self._file_table_w.setStyleSheet(f"background: {BG_CARD};")
        self._file_table_layout = QVBoxLayout(self._file_table_w)
        self._file_table_layout.setContentsMargins(0, 0, 0, 0)
        self._file_table_layout.setSpacing(0)
        body.addWidget(self._file_table_w)

        refresh_btn = QPushButton("Refresh file list")
        refresh_btn.setStyleSheet(STYLE_BTN_SMALL_GHOST)
        refresh_btn.clicked.connect(self._refresh_file_list)
        body.addWidget(refresh_btn, alignment=Qt.AlignLeft)

        shapes_row = QHBoxLayout()
        shapes_lbl = QLabel("Additional standard shapes:")
        shapes_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px; background: transparent;")
        self._num_shapes_sp = PlusMinusSpinBox()
        self._num_shapes_sp.setRange(0, 20)
        self._num_shapes_sp.setFixedWidth(70)
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

        self._sec1_err = QLabel("")
        self._sec1_err.setStyleSheet(f"color: {KS_RED}; font-size: 12px; background: transparent;")
        self._sec1_err.setVisible(False)
        body.addWidget(self._sec1_err)

        self._refresh_file_list()

    def _refresh_file_list(self):
        while self._file_table_layout.count():
            item = self._file_table_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._file_rows.clear()

        constant_dir = os.path.join(self._cwd, "constant")
        if not os.path.isdir(constant_dir):
            lbl = QLabel(f"  Not found: {constant_dir}")
            lbl.setStyleSheet(f"color: {KS_RED}; font-size: 14px; background: transparent;")
            self._file_table_layout.addWidget(lbl)
            return

        files = sorted(
            fname
            for root, dirs, fnames in os.walk(constant_dir)
            for fname in fnames
            if os.path.splitext(fname)[1].lower() in (".stl", ".obj")
        )
        if not files:
            lbl = QLabel("  No .stl/.obj files found under constant/")
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px; background: transparent;")
            self._file_table_layout.addWidget(lbl)
            return

        # Header row
        hdr = QWidget()
        hdr.setStyleSheet("background: #EEF2F8;")
        hdr_row = QHBoxLayout(hdr)
        hdr_row.setContentsMargins(10, 6, 10, 6)
        hdr_row.setSpacing(4)

        def _hdr(text, w=None):
            l = QLabel(text)
            l.setStyleSheet(
                f"color: {KS_RED}; font-size: 11px; font-weight: 700;"
                " letter-spacing: 0.4px; background: transparent;")
            if w:
                l.setFixedWidth(w)
                l.setAlignment(Qt.AlignCenter)
            else:
                l.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            return l

        hdr_row.addWidget(_hdr("FILE"))
        hdr_row.addWidget(_hdr("SURFACE TYPE", 140))
        hdr_row.addWidget(_hdr("S.MIN", 60))
        hdr_row.addWidget(_hdr("S.MAX", 60))
        hdr_row.addWidget(_hdr("VOL DIR", 94))
        hdr_row.addWidget(_hdr("V.LVL", 60))
        self._file_table_layout.addWidget(hdr)

        for i, fname in enumerate(files):
            row_bg = BG_CARD if i % 2 == 0 else "#F8FAFC"
            row_w = QWidget()
            row_w.setStyleSheet(f"background: {row_bg};")
            row_layout = QHBoxLayout(row_w)
            row_layout.setContentsMargins(10, 4, 10, 4)
            row_layout.setSpacing(4)

            name_lbl = QLabel(fname)
            name_lbl.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-family: Consolas; font-size: 13px;"
                " background: transparent;")
            name_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            row_layout.addWidget(name_lbl)

            surf_type_combo = QComboBox()
            surf_type_combo.addItems(_SURF_TYPES)
            surf_type_combo.setStyleSheet(STYLE_COMBO)
            surf_type_combo.setFixedWidth(140)
            row_layout.addWidget(surf_type_combo)

            surf_min_sp = PlusMinusSpinBox()
            surf_min_sp.setRange(0, 20)
            surf_min_sp.setFixedWidth(60)
            row_layout.addWidget(surf_min_sp)

            surf_max_sp = PlusMinusSpinBox()
            surf_max_sp.setRange(0, 20)
            surf_max_sp.setValue(1)
            surf_max_sp.setFixedWidth(60)
            row_layout.addWidget(surf_max_sp)

            vol_dir_combo = QComboBox()
            vol_dir_combo.addItems(_VOL_DIRS)
            vol_dir_combo.setStyleSheet(STYLE_COMBO)
            vol_dir_combo.setFixedWidth(94)
            row_layout.addWidget(vol_dir_combo)

            vol_level_sp = PlusMinusSpinBox()
            vol_level_sp.setRange(0, 20)
            vol_level_sp.setValue(1)
            vol_level_sp.setFixedWidth(60)
            row_layout.addWidget(vol_level_sp)

            self._file_table_layout.addWidget(row_w)

            widgets = {
                "surf_type_combo": surf_type_combo,
                "surf_min_sp":     surf_min_sp,
                "surf_max_sp":     surf_max_sp,
                "vol_dir_combo":   vol_dir_combo,
                "vol_level_sp":    vol_level_sp,
            }
            self._file_rows.append((fname, widgets))
            surf_type_combo.currentTextChanged.connect(self._refresh_layer_patches)

    # ── Standard shapes ──────────────────────────────────────────────────────────

    def _refresh_shape_fields(self):
        while self._shapes_container_layout.count():
            item = self._shapes_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._shape_widgets.clear()

        n = self._num_shapes_sp.value()
        for i in range(n):
            sub = self._sub_card(self._shapes_container_layout, f"Shape {i + 1}")
            type_combo = QComboBox()
            type_combo.addItems(["Box", "Cylinder", "Sphere"])
            type_combo.setStyleSheet(STYLE_COMBO)
            type_combo.setFixedWidth(150)
            tr = QHBoxLayout()
            tr.addWidget(QLabel("Type:"))
            tr.addWidget(type_combo)
            tr.addStretch()
            sub.addLayout(tr)

            fields_w = QWidget()
            fields_w.setStyleSheet(f"background: {BG_CARD};")
            fields_layout = QVBoxLayout(fields_w)
            fields_layout.setContentsMargins(0, 0, 0, 0)
            sub.addWidget(fields_w)

            sd = {"type_combo": type_combo, "fields_layout": fields_layout, "widgets": {}}
            self._shape_widgets.append(sd)
            type_combo.currentTextChanged.connect(lambda _, d=sd: self._rebuild_shape_fields(d))
            self._rebuild_shape_fields(sd)

    def _rebuild_shape_fields(self, sd: dict):
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
                ed.setPlaceholderText(ph); ed.setStyleSheet(STYLE_ENTRY); ed.setFixedWidth(80)
            row.addWidget(lbl); row.addWidget(vx); row.addWidget(vy); row.addWidget(vz)
            row.addStretch()
            fl.addLayout(row)
            return vx, vy, vz

        def scalar_row(label):
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;")
            lbl.setFixedWidth(140)
            ed = QLineEdit(); ed.setStyleSheet(STYLE_ENTRY); ed.setFixedWidth(100)
            row.addWidget(lbl); row.addWidget(ed); row.addStretch()
            fl.addLayout(row)
            return ed

        if t == "Box":
            w["min_x"], w["min_y"], w["min_z"] = xyz_row("Min point:")
            w["max_x"], w["max_y"], w["max_z"] = xyz_row("Max point:")
        elif t == "Cylinder":
            w["p1_x"], w["p1_y"], w["p1_z"] = xyz_row("Point 1 (axis start):")
            w["p2_x"], w["p2_y"], w["p2_z"] = xyz_row("Point 2 (axis end):")
            w["radius"] = scalar_row("Radius:")
        elif t == "Sphere":
            w["cx"], w["cy"], w["cz"] = xyz_row("Centre:")
            w["radius"] = scalar_row("Radius:")

    def _collect_shapes(self) -> list:
        shapes = []
        for i, sd in enumerate(self._shape_widgets):
            t  = sd["type_combo"].currentText()
            sw = sd["widgets"]
            sh = {"name": f"shape_{i + 1}"}
            try:
                if t == "Box":
                    sh["type"] = "searchableBox"
                    sh["min"] = [float(sw["min_x"].text()), float(sw["min_y"].text()), float(sw["min_z"].text())]
                    sh["max"] = [float(sw["max_x"].text()), float(sw["max_y"].text()), float(sw["max_z"].text())]
                elif t == "Cylinder":
                    sh["type"] = "searchableCylinder"
                    sh["point1"] = [float(sw["p1_x"].text()), float(sw["p1_y"].text()), float(sw["p1_z"].text())]
                    sh["point2"] = [float(sw["p2_x"].text()), float(sw["p2_y"].text()), float(sw["p2_z"].text())]
                    sh["radius"] = float(sw["radius"].text())
                elif t == "Sphere":
                    sh["type"] = "searchableSphere"
                    sh["centre"] = [float(sw["cx"].text()), float(sw["cy"].text()), float(sw["cz"].text())]
                    sh["radius"] = float(sw["radius"].text())
            except ValueError:
                raise ValueError(f"Shape {i + 1} ({t}): invalid numeric field")
            shapes.append(sh)
        return shapes

    # ── Section 2: Castellation ──────────────────────────────────────────────────

    def _build_sec2(self):
        card, body = build_card("02", "Castellation")
        self._content_layout.addWidget(card)

        unit_row = QHBoxLayout()
        unit_lbl = QLabel("Geometry unit:")
        unit_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px; background: transparent;")
        unit_lbl.setFixedWidth(180)
        self._geom_unit_combo = QComboBox()
        self._geom_unit_combo.addItems(_GEOM_UNITS)
        self._geom_unit_combo.setStyleSheet(STYLE_COMBO)
        self._geom_unit_combo.setFixedWidth(90)
        unit_row.addWidget(unit_lbl); unit_row.addWidget(self._geom_unit_combo); unit_row.addStretch()
        body.addLayout(unit_row)

        ncbl_row = QHBoxLayout()
        ncbl_lbl = QLabel("nCellsBetweenLevels:")
        ncbl_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px; background: transparent;")
        ncbl_lbl.setFixedWidth(180)
        self._ncbl_sp = PlusMinusSpinBox()
        self._ncbl_sp.setRange(1, 20)
        self._ncbl_sp.setValue(2)
        self._ncbl_sp.setFixedWidth(70)
        ncbl_row.addWidget(ncbl_lbl); ncbl_row.addWidget(self._ncbl_sp); ncbl_row.addStretch()
        body.addLayout(ncbl_row)

        body.addWidget(self._label_small("LOCATION IN MESH  (x, y, z)"))
        loc_row = QHBoxLayout()
        self._loc_x_ed = QLineEdit("0.0")
        self._loc_y_ed = QLineEdit("0.0")
        self._loc_z_ed = QLineEdit("0.5")
        for ed, ph in [(self._loc_x_ed, "x"), (self._loc_y_ed, "y"), (self._loc_z_ed, "z")]:
            ed.setPlaceholderText(ph); ed.setStyleSheet(STYLE_ENTRY); ed.setFixedWidth(100)
        loc_row.addWidget(self._loc_x_ed)
        loc_row.addWidget(self._loc_y_ed)
        loc_row.addWidget(self._loc_z_ed)
        loc_row.addStretch()
        body.addLayout(loc_row)

    # ── Section 3: Snap controls ─────────────────────────────────────────────────

    def _build_sec3(self):
        card, body = build_card("03", "Snap controls")
        self._content_layout.addWidget(card)

        body.addWidget(self._label_small("FEATURE SNAPPING"))
        self._snap_implicit_cb = QCheckBox(
            "Implicit feature snapping  (recommended — no edge files needed)")
        self._snap_implicit_cb.setStyleSheet(STYLE_CHECKBOX)
        self._snap_implicit_cb.setChecked(True)
        body.addWidget(self._snap_implicit_cb)

        note = QLabel(
            "When unchecked, explicitFeatureSnap is used. "
            "surfaceFeatureExtract must be run manually to generate .eMesh files first.")
        note.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; background: transparent;")
        note.setWordWrap(True)
        body.addWidget(note)

    # ── Section 4: Layer addition ────────────────────────────────────────────────

    def _build_sec4(self):
        card, body = build_card("04", "Layer addition")
        self._content_layout.addWidget(card)
        self._sec4_body = body

        self._add_layers_cb = QCheckBox("Add boundary layers?")
        self._add_layers_cb.setStyleSheet(STYLE_CHECKBOX)
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
        if self._layer_details_w:
            self._layer_details_w.setVisible(checked)
        if checked:
            self._refresh_layer_patches()
        self._update_dict_banner()

    def _get_layer_patches(self) -> list:
        """Return stems of files that have a non-None surface type."""
        return [
            os.path.splitext(fname)[0]
            for fname, widgets in self._file_rows
            if widgets["surf_type_combo"].currentText() != "None"
        ]

    def _refresh_layer_patches(self):
        if not self._layer_details_layout:
            return

        while self._layer_details_layout.count():
            item = self._layer_details_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._layer_patch_widgets.clear()

        patches = self._get_layer_patches()
        if not patches:
            lbl = QLabel(
                "  (No surfaces with a non-None Surface Type in Section 01)")
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; background: transparent;")
            self._layer_details_layout.addWidget(lbl)
            return

        hdr = QLabel("Patch stem  /  nSurfaceLayers:")
        hdr.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; background: transparent;")
        self._layer_details_layout.addWidget(hdr)

        for patch in patches:
            row = QHBoxLayout()
            lbl = QLabel(patch)
            lbl.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-family: Consolas; font-size: 13px;"
                " background: transparent;")
            lbl.setFixedWidth(260)
            sp = PlusMinusSpinBox()
            sp.setRange(0, 20); sp.setValue(3); sp.setFixedWidth(70)
            row.addWidget(lbl); row.addWidget(sp); row.addStretch()
            self._layer_details_layout.addLayout(row)
            self._layer_patch_widgets[patch] = sp

    # ── Section 5: Generate & Run ────────────────────────────────────────────────

    def _build_sec5(self):
        card, body = build_card("05", "Generate & Run")
        self._content_layout.addWidget(card)

        desc = QLabel(
            "Generates system/snappyHexMeshDict via Jinja2 template "
            "(and fvSchemes/fvSolution when layers are enabled).")
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

        sep1 = QFrame(); sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet(f"background: {BORDER_SOFT}; border: none;")
        sep1.setFixedHeight(1); body.addWidget(sep1)

        self._dict_banner = QLabel("")
        self._dict_banner.setStyleSheet("""
            QLabel {
                background: #FFF8E1; color: #7A5C00;
                border: 1px solid #F0C040; border-radius: 4px;
                padding: 5px 10px; font-size: 12px;
            }
        """)
        self._dict_banner.setWordWrap(True)
        self._dict_banner.setVisible(False)
        body.addWidget(self._dict_banner)

        gen_row = QHBoxLayout()
        self._gen_btn = QPushButton("Generate snappyHexMeshDict")
        self._gen_btn.setStyleSheet(STYLE_BTN_PRIMARY)
        self._gen_btn.clicked.connect(self._generate)
        gen_row.addStretch(); gen_row.addWidget(self._gen_btn)
        body.addLayout(gen_row)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet(f"background: {BORDER_SOFT}; border: none;")
        sep2.setFixedHeight(1); body.addWidget(sep2)

        self._snappy_banner = QLabel("")
        self._snappy_banner.setStyleSheet("""
            QLabel {
                background: #FFF8E1; color: #7A5C00;
                border: 1px solid #F0C040; border-radius: 4px;
                padding: 5px 10px; font-size: 12px;
            }
        """)
        self._snappy_banner.setWordWrap(True)
        self._snappy_banner.setVisible(False)
        body.addWidget(self._snappy_banner)

        run_row = QHBoxLayout()
        self._run_btn = QPushButton("Run snappyHexMesh")
        self._run_btn.setStyleSheet(STYLE_BTN_PRIMARY)
        self._run_btn.clicked.connect(self._run_snappy)
        run_row.addStretch(); run_row.addWidget(self._run_btn)
        body.addLayout(run_row)

        self._update_dict_banner()
        self._update_snappy_banner()
        self._update_time_dirs()

    # ── Banner/status helpers ────────────────────────────────────────────────────

    def _scan_time_dirs(self) -> list:
        try:
            return sorted(
                (e for e in os.listdir(self._cwd)
                 if e.isdigit() and os.path.isdir(os.path.join(self._cwd, e))),
                key=int)
        except Exception:
            return []

    def _update_time_dirs(self):
        if not self._time_dirs_lbl:
            return
        dirs = self._scan_time_dirs()
        if dirs:
            self._time_dirs_lbl.setText("Existing time dirs: " + "  ".join(f"/{d}" for d in dirs))
        else:
            self._time_dirs_lbl.setText("No time directories found.")

    def _update_dict_banner(self):
        if not self._dict_banner:
            return
        cwd = self._cwd
        will = []
        if os.path.isfile(os.path.join(cwd, "system", "snappyHexMeshDict")):
            will.append("system/snappyHexMeshDict")
        if self._add_layers_cb and self._add_layers_cb.isChecked():
            for fn in ("fvSchemes", "fvSolution"):
                if os.path.isfile(os.path.join(cwd, "system", fn)):
                    will.append(f"system/{fn}")
        if will:
            self._dict_banner.setText("Will overwrite: " + ",  ".join(will))
            self._dict_banner.setVisible(True)
        else:
            self._dict_banner.setVisible(False)

    def _update_snappy_banner(self):
        if not self._snappy_banner:
            return
        will = [f"/{d}/ (time dir)" for d in self._scan_time_dirs()]
        try:
            for f in os.listdir(self._cwd):
                if f.endswith(".foam"):
                    will.append(f"{f} (.foam)")
        except Exception:
            pass
        if will:
            self._snappy_banner.setText("Will overwrite: " + ",  ".join(will))
            self._snappy_banner.setVisible(True)
        else:
            self._snappy_banner.setVisible(False)

    def _change_cwd(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select OpenFOAM case directory", self._cwd)
        if not d:
            return
        self._cwd = d
        os.chdir(d)
        self._cwd_lbl.setText(d)
        if not os.path.isdir(os.path.join(d, "constant")) or not os.path.isdir(os.path.join(d, "system")):
            QMessageBox.warning(
                self, "Possible invalid case root",
                "The selected directory does not contain both constant/ and system/.\n"
                "It may not be a valid OpenFOAM case root.")
        self._refresh_file_list()
        self._update_dict_banner()
        self._update_snappy_banner()
        self._update_time_dirs()

    # ── Collect data (GUI thread only) ───────────────────────────────────────────

    def _collect_data(self) -> dict:
        """Build a fully-merged config dict from defaults.json + GUI widget values."""
        defaults = _load_defaults()

        files: list         = []
        surf_selected: list = []
        vol_selected: list  = []
        surfaces_dict: dict = {}
        vol_regions: dict   = {}

        for fname, widgets in self._file_rows:
            stem      = os.path.splitext(fname)[0]
            surf_text = widgets["surf_type_combo"].currentText()
            vol_text  = widgets["vol_dir_combo"].currentText()

            if surf_text != "None" or vol_text != "None":
                files.append(fname)

            if surf_text != "None":
                surf_selected.append(stem)
                entry: dict = {"refinementLevels": [
                    widgets["surf_min_sp"].value(),
                    widgets["surf_max_sp"].value(),
                ]}
                if surf_text == "Boundary":
                    entry["type"] = "boundary"
                elif surf_text == "FaceZone":
                    entry["type"] = "faceZone"
                elif surf_text == "FaceZone+CellZone":
                    entry["type"] = "faceZone"
                    entry["cellZoneInside"] = "inside"
                surfaces_dict[stem] = entry

            if vol_text != "None":
                vol_selected.append(stem)
                vol_regions[stem] = {
                    "mode":  "inside" if vol_text == "Inside" else "outside",
                    "level": widgets["vol_level_sp"].value(),
                }

        add_layers  = bool(self._add_layers_cb and self._add_layers_cb.isChecked())
        layers_dict: dict = {}
        if add_layers:
            for stem, sp in self._layer_patch_widgets.items():
                n = sp.value()
                if n > 0:
                    layers_dict[stem] = {"nSurfaceLayers": n}

        snap_implicit = (self._snap_implicit_cb.isChecked()
                         if self._snap_implicit_cb else True)

        override: dict = {
            "settings": {
                "geometryUnit": (self._geom_unit_combo.currentText()
                                 if self._geom_unit_combo else "mm"),
                "addLayers":    add_layers,
                "mergeTolerance":             1e-6,
                "extractRefinementFromNames": False,
            },
            "castellatedMeshControls": {
                "locationInMesh": [
                    float(self._loc_x_ed.text() or "0") if self._loc_x_ed else 0.0,
                    float(self._loc_y_ed.text() or "0") if self._loc_y_ed else 0.0,
                    float(self._loc_z_ed.text() or "0.5") if self._loc_z_ed else 0.5,
                ],
                "nCellsBetweenLevels": self._ncbl_sp.value() if self._ncbl_sp else 2,
            },
            "snapControls": {
                "implicitFeatureSnap":    snap_implicit,
                "explicitFeatureSnap":    not snap_implicit,
                "multiRegionFeatureSnap": False,
            },
            "geometry": {"files": files},
            "addLayersControls": {"layers": layers_dict},
        }

        if surf_selected:
            override["surfaceHandling"] = {
                "selectedParts": surf_selected,
                "surfaces":      surfaces_dict,
            }

        if vol_selected:
            override["volumeRefinement"] = {
                "selectedParts": vol_selected,
                "regions":       vol_regions,
            }

        shapes = self._collect_shapes()
        if shapes:
            override["geometry"]["standardShapes"] = shapes

        return deep_merge(defaults, override)

    # ── Generate ─────────────────────────────────────────────────────────────────

    def _generate(self):
        if not _BACKEND_OK:
            QMessageBox.critical(self, "Backend unavailable", _BACKEND_ERR)
            return

        cwd     = self._cwd
        sys_dir = os.path.join(cwd, "system")

        # Validate location in mesh fields
        try:
            float(self._loc_x_ed.text() or "0")
            float(self._loc_y_ed.text() or "0")
            float(self._loc_z_ed.text() or "0")
        except (ValueError, AttributeError):
            QMessageBox.critical(self, "Invalid input",
                "Location in mesh: enter three valid numbers (x, y, z).")
            return

        try:
            data = self._collect_data()
        except ValueError as e:
            QMessageBox.critical(self, "Invalid input", str(e))
            return

        geom = data.get("geometry", {})
        if not geom.get("files") and not geom.get("standardShapes"):
            QMessageBox.warning(self, "No geometry selected",
                "No geometry files are configured.\n"
                "Set Surface Type or Vol Dir for at least one file in Section 01,\n"
                "or add a standard shape.")
            return

        self._gen_btn.setEnabled(False)
        self._run_btn.setEnabled(False)
        self._log.set_running(True)
        self._log.write("\n[snappyHexMeshDict] Generating…\n", "info")

        worker = _GenerateWorker(data, sys_dir, cwd)
        worker.log_line.connect(self._log.write)
        worker.status_changed.connect(self._on_worker_status)
        worker.finished.connect(self._on_gen_done)
        worker.start()
        self._gen_worker = worker

    def _on_gen_done(self):
        self._log.set_running(False)
        self._gen_btn.setEnabled(True)
        self._run_btn.setEnabled(True)
        self._update_dict_banner()

    # ── Run snappyHexMesh ────────────────────────────────────────────────────────

    def _run_snappy(self):
        snappy = os.path.join(self._cwd, "system", "snappyHexMeshDict")
        if not os.path.isfile(snappy):
            QMessageBox.critical(self, "Missing snappyHexMeshDict",
                "system/snappyHexMeshDict not found.\nGenerate the dict first.")
            return

        self._gen_btn.setEnabled(False)
        self._run_btn.setEnabled(False)
        self._log.set_running(True)
        self._log.write("\n[snappyHexMesh] Starting…\n", "info")

        worker = _RunSnappyWorker(self._cwd)
        worker.log_line.connect(self._log.write)
        worker.status_changed.connect(self._on_worker_status)
        worker.finished.connect(self._on_run_done)
        worker.start()
        self._run_worker = worker

    def _on_run_done(self):
        self._log.set_running(False)
        self._gen_btn.setEnabled(True)
        self._run_btn.setEnabled(True)
        self._update_time_dirs()
        self._update_snappy_banner()

    def _on_worker_status(self, text: str, color: str):
        self._log.status_changed.emit(text, color)
