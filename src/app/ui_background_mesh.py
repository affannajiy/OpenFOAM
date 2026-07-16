#!/usr/bin/env python3
"""
ui_background_mesh.py — Tab 1: Background (block) mesh generator.

This tab automates the three-step process that must happen before snappyHexMesh
can run:
  1. Run OpenFOAM's surfaceCheck on the STL to get the geometry bounding box.
  2. Write system/blockMeshDict with a uniform hex grid that encloses the STL
     (padded 10 % beyond the bounding box by generateBackgroundMesh.py).
  3. Run blockMesh to create the background mesh in constant/polyMesh/.

All three steps run in _BgMeshWorker (a QThread subclass) so the GUI stays
responsive.  The worker communicates only via Qt signals — it never touches
any widget directly.
"""

import os
import sys
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QLineEdit, QScrollArea, QFrame,
                              QFileDialog, QSizePolicy)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from ui_shared import (
    KS_RED, BG_APP, BG_CARD, BORDER, TEXT_PRIMARY, TEXT_MUTED,
    STYLE_BTN_PRIMARY, STYLE_BTN_GHOST, STYLE_BTN_SMALL_GHOST, STYLE_BTN_SMALL_RED,
    STYLE_ENTRY, STYLE_SCROLL,
    build_card, positive_float, run_of_command, to_wsl_path,
    MessageBanner, scan_log_for_fix, load_prefs, save_prefs, msg_question,
)

try:
    from generateBackgroundMesh import extract_bounding_box_info, create_block_mesh_dict
    _GBM_AVAILABLE = True
except ImportError:
    _GBM_AVAILABLE = False


# ── Worker thread ──────────────────────────────────────────────────────────────

class _BgMeshWorker(QThread):
    """
    Worker thread that runs the full background mesh pipeline.

    Signals
    -------
    log_line(message, tag)        — each line of subprocess output
    status_changed(text, colour)  — overall status to propagate to the status bar
    """

    log_line       = pyqtSignal(str, str)
    status_changed = pyqtSignal(str, str)

    def __init__(self, stl_path: str, dx: float, dy: float, dz: float, cwd: str):
        super().__init__()
        self.stl_path = stl_path
        self.dx = dx
        self.dy = dy
        self.dz = dz
        self.cwd = cwd

    def _log(self, msg: str, tag: str = ""):
        """Convenience wrapper so internal code can call self._log() like a function."""
        self.log_line.emit(msg, tag)

    def run(self):
        """
        Entry point called by Qt when the thread starts.

        Sequence
        --------
        1. Run surfaceCheck, collect all stdout lines into output_lines for
           later parsing while also forwarding them live to the log.
        2. Write the surfaceCheck output to programOutputs/ for offline review.
        3. Parse the bounding box from the collected output.
        4. Call create_block_mesh_dict() (from generateBackgroundMesh.py) to
           write system/blockMeshDict.
        5. Run blockMesh.
        6. Remove any stale .foam files and create a fresh one named after the
           case directory so ParaView can find the mesh.
        """
        self.status_changed.emit("Running...", "#F59E0B")
        cwd = self.cwd
        sys_dir = os.path.join(cwd, "system")
        out_dir = os.path.join(cwd, "programOutputs")

        try:
            os.makedirs(out_dir, exist_ok=True)

            # ── surfaceCheck ─────────────────────────────────────────────────
            self._log("[Background Mesh] Running surfaceCheck…\n", "info")
            output_lines: list[str] = []

            # Closure that simultaneously forwards each line to the log AND
            # stores it so we can parse the full output after the command ends.
            def log_and_collect(line: str, tag: str = ""):
                output_lines.append(line)
                self._log(line, tag)

            rc = run_of_command(f"surfaceCheck {self.stl_path}", cwd, log_and_collect)
            if rc != 0:
                self._log(f"[Background Mesh] surfaceCheck exited with code {rc}\n", "error")
                self.status_changed.emit("Error — check log", "#EF4444")
                return

            output = "".join(output_lines)

            # Write log file
            tmp_file = os.path.join(out_dir, "surfaceCheck_blockMesh.log")
            with open(tmp_file, "w") as f:
                f.write(output)

            # ── Parse bounding box ───────────────────────────────────────────
            if _GBM_AVAILABLE:
                bbox = extract_bounding_box_info(output)
            else:
                import re
                pat = re.compile(
                    r"Bounding Box : \((-?\S+) (-?\S+) (-?\S+)\) \((-?\S+) (-?\S+) (-?\S+)\)")
                m = pat.search(output)
                bbox = tuple(map(float, m.groups())) if m else None

            if not bbox:
                self._log("[Background Mesh] Could not parse bounding box.\n", "error")
                self.status_changed.emit("Error — check log", "#EF4444")
                return

            # ── Write blockMeshDict ──────────────────────────────────────────
            self._log("[Background Mesh] Writing blockMeshDict…\n", "info")
            if not os.path.isdir(sys_dir):
                self._log("[Background Mesh] ERROR: system/ folder not found in case dir.\n", "error")
                self.status_changed.emit("Error — check log", "#EF4444")
                return

            if _GBM_AVAILABLE:
                create_block_mesh_dict(sys_dir, bbox, self.dx, self.dy, self.dz)
            else:
                self._log("[Background Mesh] generateBackgroundMesh not importable; skipping dict write.\n", "warn")

            # ── blockMesh ────────────────────────────────────────────────────
            self._log("[Background Mesh] Running blockMesh…\n", "info")
            rc = run_of_command("blockMesh", cwd, self._log)
            if rc != 0:
                self._log(f"[Background Mesh] blockMesh exited with code {rc}\n", "error")
                self.status_changed.emit("Error — check log", "#EF4444")
                return

            # ── Clean slate for ParaView: remove snappy time dirs + stale .foam ──
            # A new background mesh is a fresh start — any previous snappyHexMesh
            # outputs (numbered time directories) are stale and would confuse ParaView.
            for entry in os.listdir(cwd):
                entry_path = os.path.join(cwd, entry)
                if entry.isdigit() and os.path.isdir(entry_path):
                    try:
                        shutil.rmtree(entry_path)
                        self._log(f"[Background Mesh] Removed stale time dir: {entry}/\n", "info")
                    except Exception:
                        pass
                elif entry.endswith(".foam"):
                    try:
                        os.remove(entry_path)
                    except Exception:
                        pass
            case_name = os.path.basename(cwd)
            foam_path = os.path.join(cwd, f"{case_name}.foam")
            open(foam_path, "w").close()
            self._log(f"[Background Mesh] Created: {foam_path}\n", "info")
            self._log("[Background Mesh] Done.\n", "info")
            self.status_changed.emit("Done", "#22C55E")

        except Exception as exc:
            self._log(f"[Background Mesh] Exception: {exc}\n", "error")
            self.status_changed.emit("Error — check log", "#EF4444")


# ── Tab widget ─────────────────────────────────────────────────────────────────

class BackgroundMeshWidget(QWidget):
    """
    Tab 1 widget — Background (block) mesh generator.

    Contains two input cards (STL path, grid resolution), a warning banner
    that lists files that will be overwritten, and a Generate / Cancel action
    row.  All heavy work is delegated to _BgMeshWorker.
    """

    # Emitted when the user clicks "Continue to Snappy Hex Mesh" on the success
    # banner; MainWindow connects this to switch to the Snappy tab.
    request_snappy = pyqtSignal()

    def __init__(self, log_drawer, parent=None):
        super().__init__(parent)
        self._log      = log_drawer  # LogDrawer instance shared with other tabs
        self._worker   = None        # holds the active QThread, or None
        self._run_log  = []          # collected output lines for error scanning
        self._last_color = ""        # last status colour reported by the worker
        self.setStyleSheet(f"background: {BG_APP};")
        self._build()

    # ── Layout ─────────────────────────────────────────────────────────────────

    def _build(self):
        """Assemble the tab: scrollable column holding Card A (STL path),
        Card B (DX/DY/DZ grid sizes), the yellow overwrite banner, the
        green/red result banner, and the Cancel / Generate action row."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(STYLE_SCROLL)
        outer.addWidget(scroll)

        content = QWidget()
        content.setStyleSheet(f"background: {BG_APP};")
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # ── Card A: STL file ──────────────────────────────────────────────────
        card_a, body_a = build_card("A", "STL file")
        layout.addWidget(card_a)

        lbl_a = QLabel("PATH")
        lbl_a.setStyleSheet(
            f"color: {TEXT_MUTED}; font-family: 'Segoe UI'; font-size: 12px;"
            " font-weight: 600; letter-spacing: 0.5px; background: transparent;")
        body_a.addWidget(lbl_a)

        stl_row = QHBoxLayout()
        stl_row.setSpacing(8)
        self._stl_edit = QLineEdit()
        self._stl_edit.setPlaceholderText("constant/.../geometry.stl")
        self._stl_edit.setStyleSheet(STYLE_ENTRY)
        self._stl_edit.setToolTip(
            "STL that sets the domain size. Its bounding box\n"
            "becomes the background block. Case root is auto-detected\n"
            "from constant/ in the path.")
        self._stl_edit.textChanged.connect(self._update_overwrite_banner)

        browse_btn = QPushButton("Browse…")
        browse_btn.setStyleSheet(STYLE_BTN_SMALL_RED)
        browse_btn.setToolTip("Pick the STL file from disk.")
        browse_btn.clicked.connect(self._browse)

        stl_row.addWidget(self._stl_edit)
        stl_row.addWidget(browse_btn)
        body_a.addLayout(stl_row)

        self._stl_err = QLabel("")
        self._stl_err.setStyleSheet(f"color: {KS_RED}; font-size: 13px; background: transparent;")
        self._stl_err.setVisible(False)
        body_a.addWidget(self._stl_err)

        # ── Card B: Grid resolution ───────────────────────────────────────────
        card_b, body_b = build_card("B", "Grid resolution")
        layout.addWidget(card_b)

        grid_row = QHBoxLayout()
        grid_row.setSpacing(16)
        self._d_edits: dict[str, QLineEdit] = {}
        self._d_errs:  dict[str, QLabel]    = {}

        for name, label in [("dx", "DX (mm)"), ("dy", "DY (mm)"), ("dz", "DZ (mm)")]:
            col = QVBoxLayout()
            col.setSpacing(4)
            lbl = QLabel(label)
            lbl.setStyleSheet(
                f"color: {TEXT_MUTED}; font-family: 'Segoe UI'; font-size: 12px;"
                " font-weight: 600; letter-spacing: 0.5px; background: transparent;")
            edit = QLineEdit()
            edit.setPlaceholderText("0.05")
            edit.setStyleSheet(STYLE_ENTRY)
            edit.setToolTip(
                f"Background cell size along {name[1].upper()} (mm).\n"
                "Smaller = finer base mesh, more cells.\n"
                "Keep DX, DY, DZ equal for cube-shaped cells.")
            err = QLabel("")
            err.setStyleSheet(f"color: {KS_RED}; font-size: 12px; background: transparent;")
            err.setVisible(False)
            col.addWidget(lbl)
            col.addWidget(edit)
            col.addWidget(err)
            grid_row.addLayout(col)
            self._d_edits[name] = edit
            self._d_errs[name]  = err

        body_b.addLayout(grid_row)

        # ── Overwrite banner ──────────────────────────────────────────────────
        self._overwrite_banner = QLabel("")
        self._overwrite_banner.setStyleSheet(f"""
            QLabel {{
                background: #FFF8E1;
                color: #7A5C00;
                border: 1px solid #F0C040;
                border-radius: 4px;
                padding: 6px 10px;
                font-family: 'Segoe UI';
                font-size: 13px;
            }}
        """)
        self._overwrite_banner.setWordWrap(True)
        self._overwrite_banner.setVisible(False)
        layout.addWidget(self._overwrite_banner)

        # ── Result banner (red error+fix / green success+handoff) ─────────────
        self._msg_banner = MessageBanner()
        layout.addWidget(self._msg_banner)

        # ── Action row ────────────────────────────────────────────────────────
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(STYLE_BTN_GHOST)
        cancel_btn.setToolTip("Stop a running job and clear all inputs.")
        cancel_btn.clicked.connect(self._cancel)

        self._gen_btn = QPushButton("Generate Background Mesh →")
        self._gen_btn.setStyleSheet(STYLE_BTN_PRIMARY)
        self._gen_btn.setToolTip(
            "Runs surfaceCheck, writes blockMeshDict, runs blockMesh.\n"
            "Creates the background block the mesh is carved from.\n"
            "Do this before the SnappyHexMesh tab.")
        self._gen_btn.clicked.connect(self._run)

        action_row.addWidget(cancel_btn)
        action_row.addStretch()
        action_row.addWidget(self._gen_btn)
        layout.addLayout(action_row)

        layout.addStretch()
        self._update_overwrite_banner()

        # Restore last-used grid sizes from the per-user prefs file so a
        # returning user does not have to re-type them every launch.
        prefs = load_prefs()
        for name in ("dx", "dy", "dz"):
            val = prefs.get(f"bg_{name}")
            if val is not None and positive_float(val) is not None:
                self._d_edits[name].setText(str(val))

    # ── Slots ──────────────────────────────────────────────────────────────────

    def set_case_dir(self, case_dir: str):
        """Called by MainWindow when the user picks a project on the landing page."""
        case_dir = to_wsl_path(case_dir)
        # Scan constant/ recursively for the first STL file and pre-fill the path.
        stl_path = None
        constant_dir = os.path.join(case_dir, "constant")
        if os.path.isdir(constant_dir):
            for root, _dirs, files in os.walk(constant_dir):
                for fname in sorted(files):
                    if fname.lower().endswith(".stl"):
                        stl_path = os.path.join(root, fname)
                        break
                if stl_path:
                    break
        if stl_path:
            self._stl_edit.setText(stl_path)
            self._log.write(
                f"[Background Mesh] Auto-detected STL: {stl_path}\n", "info")
        self._update_overwrite_banner()

    def _browse(self):
        """Open a file dialog for the STL. If the picked file lives under a
        case's constant/ folder, offer to switch the working directory to that
        case root so all later commands run in the right place."""
        start_dir = os.getcwd()
        # Start inside constant/ so the user lands near the STL files.
        constant_dir = os.path.join(start_dir, "constant")
        if os.path.isdir(constant_dir):
            start_dir = constant_dir
        p, _ = QFileDialog.getOpenFileName(
            self, "Select STL file", start_dir,
            "STL files (*.stl);;All files (*.*)")
        if not p:
            return
        p = to_wsl_path(p)
        self._stl_edit.setText(p)

        # If the selected file is anywhere under .../constant/, the directory
        # one level above constant/ is the OpenFOAM case root.  We offer to
        # chdir() there automatically so the user doesn't have to set it manually.
        norm = p.replace("\\", "/")
        marker = "/constant/"
        idx = norm.lower().rfind(marker)
        inferred = p[:idx] if idx >= 0 else os.path.dirname(p)

        if inferred != os.getcwd():
            if msg_question(
                    self, "Change working directory?",
                    f"Detected case root:\n  {inferred}\n\n"
                    "Change the working directory to this location?"):
                os.chdir(inferred)
                self._log.write(
                    f"[Background Mesh] Case directory set to: {inferred}\n", "info")
        self._update_overwrite_banner()

    def _update_overwrite_banner(self):
        """
        Refresh the yellow warning banner listing files that will be overwritten.

        Called whenever the STL path or case directory changes so the user always
        knows what will be replaced before clicking Generate.  Includes snappyHexMesh
        time-directory outputs because a fresh background mesh wipes them.
        """
        cwd = os.getcwd()
        will_overwrite = []

        for rel in [("system", "blockMeshDict"),
                    ("programOutputs", "blockMesh.log"),
                    ("programOutputs", "surfaceCheck_blockMesh.log")]:
            if os.path.isfile(os.path.join(cwd, *rel)):
                will_overwrite.append("/".join(rel))
        if os.path.isdir(os.path.join(cwd, "constant", "polyMesh")):
            will_overwrite.append("constant/polyMesh/")

        # Snappy outputs (time dirs and .foam) will also be cleared for a clean slate
        try:
            time_dirs = sorted(
                e for e in os.listdir(cwd)
                if e.isdigit() and os.path.isdir(os.path.join(cwd, e)))
            if time_dirs:
                will_overwrite.append(
                    "time dirs: " + " ".join(f"/{d}" for d in time_dirs)
                    + " (snappyHexMesh output)")
            for f in os.listdir(cwd):
                if f.endswith(".foam"):
                    will_overwrite.append(f"{f} (.foam)")
                    break
        except OSError:
            pass

        if will_overwrite:
            self._overwrite_banner.setText(
                "⚠  Will overwrite: " + ",  ".join(will_overwrite))
            self._overwrite_banner.setVisible(True)
        else:
            self._overwrite_banner.setVisible(False)

    def _validate(self) -> bool:
        """
        Validate all inputs and show inline error labels on failure.

        Returns True only when both the STL path resolves to an existing file
        and all three grid sizes are strictly positive floats.
        """
        ok = True
        self._stl_err.setVisible(False)
        for e in self._d_errs.values():
            e.setVisible(False)

        stl = self._stl_edit.text().strip()
        if not stl:
            self._stl_err.setText("Required")
            self._stl_err.setVisible(True)
            ok = False
        elif not os.path.isfile(stl):
            self._stl_err.setText("File not found")
            self._stl_err.setVisible(True)
            ok = False

        for name in ("dx", "dy", "dz"):
            v = self._d_edits[name].text().strip()
            if not v:
                self._d_errs[name].setText("Required")
                self._d_errs[name].setVisible(True)
                ok = False
            elif positive_float(v) is None:
                self._d_errs[name].setText("Must be positive")
                self._d_errs[name].setVisible(True)
                ok = False
        return ok

    def _run(self):
        """Validate inputs, then start _BgMeshWorker to run surfaceCheck + blockMesh."""
        if self._worker and self._worker.isRunning():
            return
        if not self._validate():
            return

        cwd = os.getcwd()
        stl = self._stl_edit.text().strip()
        dx  = float(self._d_edits["dx"].text())
        dy  = float(self._d_edits["dy"].text())
        dz  = float(self._d_edits["dz"].text())

        # Remember the grid sizes for the next app launch.
        save_prefs({"bg_dx": dx, "bg_dy": dy, "bg_dz": dz})

        self._gen_btn.setEnabled(False)
        self._log.set_running(True)
        self._log.write("\n[Background Mesh] Starting…\n", "info")

        # Reset per-run state for the result banner.
        self._run_log = []
        self._last_color = ""
        self._msg_banner.hide_msg()

        self._worker = _BgMeshWorker(stl, dx, dy, dz, cwd)
        self._worker.log_line.connect(self._log.write)
        self._worker.log_line.connect(self._collect_log)
        self._worker.status_changed.connect(self._on_worker_status)
        self._worker.finished.connect(self._on_worker_done)
        self._worker.start()

    def _collect_log(self, line: str, _tag: str = ""):
        """Accumulate worker output so a failed run can be scanned for a plain fix."""
        self._run_log.append(line)

    def _on_worker_status(self, text: str, color: str):
        """Remember the worker's latest status colour (decides success/error
        banner later) and forward it to the status bar."""
        self._last_color = color
        self._log.status_changed.emit(text, color)

    def _on_worker_done(self):
        """Worker finished (any outcome): stop the running animation, re-enable
        Generate, and show the result banner — green with a 'Continue to
        Snappy' button on success, red with a plain-words fix on failure."""
        self._log.set_running(False)
        self._gen_btn.setEnabled(True)
        self._update_overwrite_banner()

        if self._last_color == "#22C55E":
            # Success — offer the next step.
            self._msg_banner.show_success(
                "Background mesh created. Next: build the mesh around your geometry.",
                "Continue to Snappy Hex Mesh →",
                self.request_snappy.emit)
        elif self._last_color == "#EF4444":
            fix = scan_log_for_fix("".join(self._run_log))
            self._msg_banner.show_error(
                fix or "Background mesh failed. Open the log below and read the last "
                "few red lines to see what went wrong.")

    def cancel_run(self):
        """Esc shortcut entry: stop a running job only — never touches the
        typed inputs (unlike the Cancel button, which also clears the form)."""
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._log.write("[Background Mesh] Cancelled.\n", "warn")
            self._log.set_running(False)
            self._gen_btn.setEnabled(True)
            self._log.status_changed.emit("Cancelled", "#F59E0B")

    def _cancel(self):
        """Cancel button: stop a running job if there is one, otherwise ask
        before wiping the user's typed inputs, then clear everything."""
        running = bool(self._worker and self._worker.isRunning())
        if not running:
            has_input = bool(
                self._stl_edit.text().strip()
                or any(e.text().strip() for e in self._d_edits.values()))
            if has_input:
                if not msg_question(
                        self, "Clear inputs?",
                        "This clears the STL path and grid sizes you entered. "
                        "Continue?"):
                    return
        if running:
            self._worker.terminate()
            self._log.write("[Background Mesh] Cancelled.\n", "warn")
            self._log.set_running(False)
            self._gen_btn.setEnabled(True)
        # Clear all inputs
        self._stl_edit.clear()
        for ed in self._d_edits.values():
            ed.clear()
        for e in self._d_errs.values():
            e.setVisible(False)
        self._stl_err.setVisible(False)
        self._overwrite_banner.setVisible(False)
        self._msg_banner.hide_msg()
