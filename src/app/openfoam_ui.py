#!/usr/bin/env python3
"""
openfoam_ui.py — Main window and entry point for the OpenFOAM GUI.

This file is intentionally thin: it builds the chrome (header, hero strip,
status bar) and wires everything together, but contains no CFD logic.  All
mesh generation and snappyHexMeshDict building happens in the tab widgets.

Window layout (fixed heights except the stack which stretches)
──────────────────────────────────────────────────────────────
 Header bar  52 px  — logo, app name, CWD basename, tab pills, Open ParaView
 Hero strip  80 px  — per-tab eyebrow/title/subtitle + WORKING DIR badge
 Stack       flex   — QStackedWidget holding BackgroundMeshWidget / SnappyHexWidget
 LogDrawer   36 px+ — collapsible/resizable log; drag bottom edge to resize
 Status bar  24 px  — blinking dot + status text (left); CWD path (right)

Running
-------
  cd /mnt/c/OpenFOAM/03_mesh_session
  python3 /mnt/c/OpenFOAM/src/app/openfoam_ui.py
"""

import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                              QHBoxLayout, QLabel, QPushButton, QFrame,
                              QStackedWidget)
from PyQt5.QtWidgets import QShortcut
from PyQt5.QtCore import Qt, QTimer, qInstallMessageHandler
from PyQt5.QtGui import QIcon, QPixmap, QKeySequence


# Qt5 on Linux/WSL emits "Could not parse stylesheet of object QFrame(...)" to
# stderr for QFrame widgets whose QSS uses border-radius inside a QScrollArea
# hierarchy — even though the styles are applied correctly.  The handler below
# silences those specific messages while forwarding all other Qt diagnostics
# (warnings, critical errors) to stderr as normal.  Installed at module load
# time so it is active before QApplication is created.
def _qt_msg_handler(msg_type, context, message):
    if "Could not parse stylesheet" not in message:
        sys.stderr.write(message + "\n")


qInstallMessageHandler(_qt_msg_handler)

from ui_shared import (
    KS_RED, KS_BLACK, BG_APP, TEXT_PRIMARY, TEXT_MUTED, TEXT_WHITE,
    LOG_CMD, BORDER, STYLE_TOOLTIP,
    find_paraview_exe, msg_info,
)
from ui_log_drawer import LogDrawer
from ui_background_mesh import BackgroundMeshWidget
from ui_snappy_hex import SnappyHexWidget
from ui_landing import LandingWidget


# ── Tab metadata ───────────────────────────────────────────────────────────────

_TABS = [
    {
        "label":    "Background Mesh",
        "eyebrow":  "STEP 1 OF 2",
        "title":    "Background Mesh",
        "subtitle": "Generate blockMeshDict from STL bounding box and run blockMesh.",
    },
    {
        "label":    "Snappy Hex Mesh",
        "eyebrow":  "STEP 2 OF 2",
        "title":    "Snappy Hex Mesh",
        "subtitle": "Configure and generate snappyHexMeshDict, then run snappyHexMesh.",
    },
]


# ── Main window ────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    """
    Top-level application window.

    Responsibilities
    ----------------
    • Build and own all chrome widgets (header, hero, status bar).
    • Instantiate the two tab content widgets and the shared LogDrawer.
    • Drive tab switching: update the QStackedWidget, repaint tab pills,
      and update the hero strip text.
    • Refresh the CWD display every 2 seconds via QTimer so the badge
      always reflects the current working directory (which the tab widgets
      may change via os.chdir when the user browses for a case root).
    • Launch ParaView on Windows by converting the WSL .foam path to a
      Windows UNC path with wslpath -w.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenFOAM GUI")
        self.resize(1280, 720)   # 720p (HD) default, centered by _center()
        self._tab_idx = 0

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._log = LogDrawer()

        # Header is always visible (includes ← Home button)
        self._build_header(root)

        # Root stack: index 0 = landing, index 1 = utility UI
        self._root_stack = QStackedWidget()
        root.addWidget(self._root_stack, 1)

        # Index 0 — Landing page
        self._landing = LandingWidget()
        self._landing.continue_clicked.connect(self.show_utility)
        self._root_stack.addWidget(self._landing)

        # Index 1 — Utility UI (hero + tab stack + log)
        utility_widget = QWidget()
        utility_widget.setStyleSheet(f"background: {BG_APP};")
        util_layout = QVBoxLayout(utility_widget)
        util_layout.setContentsMargins(0, 0, 0, 0)
        util_layout.setSpacing(0)
        self._build_hero(util_layout)
        self._build_stack(util_layout)
        util_layout.addWidget(self._log)
        self._root_stack.addWidget(utility_widget)

        # Status bar is always visible
        self._build_statusbar(root)

        self._log.status_changed.connect(self._on_status_changed)

        self._last_utility_index = 0
        self._has_active_session = False

        self._cwd_timer = QTimer(self)
        self._cwd_timer.timeout.connect(self._refresh_cwd)
        self._cwd_timer.start(2000)

        self._landing.return_clicked.connect(self._on_return)
        self._root_stack.currentChanged.connect(self._update_header_visibility)

        self._refresh_cwd()
        self._switch_tab(0)

        # Start on landing page — header visibility controlled by _update_header_visibility
        self._root_stack.setCurrentIndex(0)
        self._update_header_visibility(0)

        self._set_window_icon()
        self._center()
        self._install_shortcuts()

    # ── Keyboard shortcuts + Help ──────────────────────────────────────────────

    def _install_shortcuts(self):
        """App-wide keyboard accelerators: F1 = help, Ctrl+L = toggle log
        drawer, Esc = stop the active tab's running job (no-op when idle)."""
        QShortcut(QKeySequence("F1"),     self, activated=self._show_help)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self._log._toggle)
        QShortcut(QKeySequence("Esc"),    self, activated=self._cancel_active_run)

    def _cancel_active_run(self):
        """Esc: cancel whichever tab has a job running; does nothing when idle."""
        if self._root_stack.currentIndex() != 1:
            return
        if self._tab_idx == 0:
            self._bg_widget.cancel_run()
        else:
            self._snappy_widget.cancel_run()

    def _show_help(self):
        """Quick-start help dialog (? header button / F1)."""
        msg_info(
            self, "Quick start",
            "<b>1 — Background Mesh (Step 1 of 2)</b><br>"
            "• Pick your STL file, set the cell sizes DX/DY/DZ (mm).<br>"
            "• Click <i>Generate Background Mesh</i> — this builds the box "
            "your part will be meshed inside.<br><br>"
            "<b>2 — Snappy Hex Mesh (Step 2 of 2)</b><br>"
            "• In the file table: the outer shell = <i>Boundary</i>; every solid "
            "inside it = <i>FaceZone</i> + Cell Zone, Vol Dir = Inside.<br>"
            "• Set <i>Location In Mesh</i> to a point inside the box but outside "
            "the solids (use <i>Suggest point</i>).<br>"
            "• Check the PRE-FLIGHT list shows all ✓, then click Generate.<br><br>"
            "<b>Shortcuts</b><br>"
            "• F1 — this help &nbsp;• Ctrl+L — show/hide log &nbsp;"
            "• Esc — stop a running job<br><br>"
            "Hover over any field for a hint. When a run fails, the red banner "
            "above the log tells you the fix in plain words.")

    # ── Header bar ─────────────────────────────────────────────────────────────

    def _build_header(self, root: QVBoxLayout):
        """Build the black 52 px header bar: ← Home, logo, app name, CWD badge,
        tab pills, and the Open ParaView button. Items that only make sense
        inside a project are hidden on the landing page
        (see _update_header_visibility)."""
        hdr = QWidget()
        hdr.setFixedHeight(52)
        hdr.setStyleSheet(f"background: {KS_BLACK};")
        row = QHBoxLayout(hdr)
        row.setContentsMargins(20, 0, 20, 0)
        row.setSpacing(10)

        _icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")

        # ← Home button — hidden on landing page
        self._home_btn = QPushButton("← Home")
        self._home_btn.setCursor(Qt.PointingHandCursor)
        self._home_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: #9CA3AF;
                border: none;
                border-radius: 4px;
                padding: 5px 10px;
                font-family: 'Segoe UI';
                font-size: 11px;
            }}
            QPushButton:hover {{ color: {TEXT_WHITE}; }}
        """)
        self._home_btn.setToolTip("Back to the landing page to switch project or utility.")
        self._home_btn.clicked.connect(self.show_landing)
        row.addWidget(self._home_btn)

        logo = QLabel()
        _logo_pix = os.path.join(_icons_dir, "icon_32.png")
        if os.path.exists(_logo_pix):
            logo.setPixmap(
                QPixmap(_logo_pix).scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setFixedSize(20, 20)
        logo.setStyleSheet("background: transparent;")
        row.addWidget(logo)

        app_lbl = QLabel("OpenFOAM GUI")
        app_lbl.setStyleSheet(
            f"color: {TEXT_WHITE}; font-family: 'Segoe UI'; font-size: 14px;"
            " font-weight: 600; background: transparent;")
        row.addWidget(app_lbl)

        # CWD badge (/ + path) — hidden on landing page
        self._cwd_badge = QWidget()
        self._cwd_badge.setStyleSheet("background: transparent;")
        badge_layout = QHBoxLayout(self._cwd_badge)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_layout.setSpacing(6)
        sep_slash = QLabel("/")
        sep_slash.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 14px; background: transparent;")
        badge_layout.addWidget(sep_slash)
        self._cwd_lbl = QLabel("")
        self._cwd_lbl.setStyleSheet(
            f"color: {LOG_CMD}; font-family: Consolas; font-size: 12px;"
            " background: transparent;")
        badge_layout.addWidget(self._cwd_lbl)
        row.addWidget(self._cwd_badge)

        row.addStretch()

        # Tab pills + separator — hidden on landing page
        self._tab_pills_widget = QWidget()
        self._tab_pills_widget.setStyleSheet("background: transparent;")
        pills_layout = QHBoxLayout(self._tab_pills_widget)
        pills_layout.setContentsMargins(0, 0, 0, 0)
        pills_layout.setSpacing(10)

        self._tab_btns: list[QPushButton] = []
        for i, tab in enumerate(_TABS):
            btn = QPushButton(tab["label"])
            btn.setFixedHeight(32)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(tab["subtitle"])
            btn.clicked.connect(lambda checked, idx=i: self._switch_tab(idx))
            self._tab_btns.append(btn)
            pills_layout.addWidget(btn)

        sep_line = QFrame()
        sep_line.setFixedWidth(1)
        sep_line.setStyleSheet("QFrame { background: #374151; }")
        pills_layout.addSpacing(8)
        pills_layout.addWidget(sep_line)
        pills_layout.addSpacing(8)
        row.addWidget(self._tab_pills_widget)

        # Open ParaView button — hidden on landing page
        self._paraview_btn = QPushButton("● Open ParaView")
        self._paraview_btn.setStyleSheet(f"""
            QPushButton {{
                color: {TEXT_WHITE};
                background: transparent;
                border: 1px solid #374151;
                border-radius: 4px;
                padding: 5px 14px;
                font-family: 'Segoe UI';
                font-size: 12px;
            }}
            QPushButton:hover {{ border-color: {LOG_CMD}; }}
            QPushButton:disabled {{ color: #6B7280; border-color: #374151; }}
        """)
        self._paraview_btn.setToolTip(
            "Open the current case in ParaView to inspect the mesh.\n"
            "ParaView must be installed on Windows.")
        self._paraview_btn.setEnabled(False)
        self._paraview_btn.clicked.connect(self._open_paraview)
        row.addWidget(self._paraview_btn)

        # Help button — always visible, opens the quick-start dialog (also F1).
        help_btn = QPushButton("?")
        help_btn.setFixedSize(26, 26)
        help_btn.setCursor(Qt.PointingHandCursor)
        help_btn.setStyleSheet(f"""
            QPushButton {{
                color: #9CA3AF;
                background: transparent;
                border: 1px solid #374151;
                border-radius: 13px;
                font-family: 'Segoe UI';
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ color: {TEXT_WHITE}; border-color: {LOG_CMD}; }}
        """ + STYLE_TOOLTIP)
        help_btn.setToolTip("Quick-start help (F1).")
        help_btn.clicked.connect(self._show_help)
        row.addWidget(help_btn)

        root.addWidget(hdr)

    # ── Hero strip ─────────────────────────────────────────────────────────────

    def _build_hero(self, root: QVBoxLayout):
        """Build the 80 px hero strip under the header: step eyebrow, tab title
        and subtitle on the left; WORKING DIR badge on the right. Text is
        swapped per tab by _switch_tab."""
        hero = QWidget()
        hero.setFixedHeight(80)
        hero.setStyleSheet(f"background: {BG_APP}; border-bottom: 1px solid {BORDER};")
        row = QHBoxLayout(hero)
        row.setContentsMargins(24, 0, 24, 0)
        row.setSpacing(0)

        left = QVBoxLayout()
        left.setSpacing(2)
        left.setAlignment(Qt.AlignVCenter)

        self._hero_eyebrow = QLabel("")
        self._hero_eyebrow.setStyleSheet(
            f"color: {KS_RED}; font-family: Consolas; font-size: 10px;"
            " font-weight: bold; background: transparent; letter-spacing: 1px;")
        left.addWidget(self._hero_eyebrow)

        self._hero_title = QLabel("")
        self._hero_title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-family: 'Segoe UI'; font-size: 18px;"
            " font-weight: 600; background: transparent;")
        left.addWidget(self._hero_title)

        self._hero_subtitle = QLabel("")
        self._hero_subtitle.setStyleSheet(
            f"color: {TEXT_MUTED}; font-family: 'Segoe UI'; font-size: 12px;"
            " background: transparent;")
        left.addWidget(self._hero_subtitle)

        row.addLayout(left)
        row.addStretch()

        right = QVBoxLayout()
        right.setSpacing(4)
        right.setAlignment(Qt.AlignVCenter | Qt.AlignRight)

        wd_lbl = QLabel("WORKING DIR")
        wd_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-family: 'Segoe UI'; font-size: 10px;"
            " font-weight: 600; letter-spacing: 0.5px; background: transparent;")
        wd_lbl.setAlignment(Qt.AlignRight)
        right.addWidget(wd_lbl)

        self._hero_cwd = QLabel("")
        self._hero_cwd.setStyleSheet(f"""
            QLabel {{
                background: {KS_BLACK};
                color: {TEXT_WHITE};
                font-family: Consolas;
                font-size: 11px;
                border-radius: 3px;
                padding: 3px 8px;
            }}
        """)
        self._hero_cwd.setAlignment(Qt.AlignRight)
        right.addWidget(self._hero_cwd)

        row.addLayout(right)
        root.addWidget(hero)

    # ── Content stack ──────────────────────────────────────────────────────────

    def _build_stack(self, root: QVBoxLayout):
        """Create the two tab content widgets (Background Mesh, Snappy Hex
        Mesh) inside a QStackedWidget. Both share the same LogDrawer. The
        Background tab's green success banner can jump straight to the Snappy
        tab via the request_snappy signal."""
        self._stack = QStackedWidget()
        self._stack.setMinimumHeight(0)   # allow the log drawer to push upward
        self._bg_widget     = BackgroundMeshWidget(self._log)
        self._snappy_widget = SnappyHexWidget(self._log)
        self._bg_widget.request_snappy.connect(lambda: self._switch_tab(1))
        self._stack.addWidget(self._bg_widget)
        self._stack.addWidget(self._snappy_widget)
        root.addWidget(self._stack, 1)

    # ── Status bar ─────────────────────────────────────────────────────────────

    def _build_statusbar(self, root: QVBoxLayout):
        """Build the black 24 px status bar: coloured dot + status text on the
        left (driven by the LogDrawer's status_changed signal), full CWD path
        on the right."""
        sb = QWidget()
        sb.setFixedHeight(24)
        sb.setStyleSheet(f"background: {KS_BLACK};")
        row = QHBoxLayout(sb)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(6)

        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet(
            "color: #22C55E; font-size: 9px; background: transparent;")
        row.addWidget(self._status_dot)

        self._status_lbl = QLabel("Ready")
        self._status_lbl.setStyleSheet(
            f"color: {TEXT_WHITE}; font-family: 'Segoe UI'; font-size: 11px;"
            " background: transparent;")
        row.addWidget(self._status_lbl)

        row.addStretch()

        self._sb_cwd = QLabel("")
        self._sb_cwd.setStyleSheet(
            f"color: {LOG_CMD}; font-family: Consolas; font-size: 11px;"
            " background: transparent;")
        row.addWidget(self._sb_cwd)

        root.addWidget(sb)

    # ── Landing / utility navigation ───────────────────────────────────────────

    def show_landing(self):
        """Return to the landing page."""
        self._root_stack.setCurrentIndex(0)
        self._landing.refresh_recents()
        self._update_landing_session_state()

    def show_utility(self, case_dir: str, util_id: int):
        """Switch to the utility UI at the given tab and case directory."""
        try:
            os.chdir(case_dir)
        except Exception:
            pass
        self._bg_widget.set_case_dir(case_dir)
        self._snappy_widget.set_case_dir(case_dir)
        self._has_active_session = True
        self._root_stack.setCurrentIndex(1)
        self._switch_tab(util_id)
        self._refresh_cwd()
        self._update_landing_session_state()

    def _update_header_visibility(self, page_index: int):
        """Show or hide context-sensitive header items based on which page is active."""
        on_landing = (page_index == 0)
        self._home_btn.setVisible(not on_landing)
        self._tab_pills_widget.setVisible(not on_landing)
        self._paraview_btn.setVisible(not on_landing)
        self._cwd_badge.setVisible(not on_landing)

    def _on_return(self):
        """Jump back to the utility page without resetting case dir or widget state."""
        self._root_stack.setCurrentIndex(1)
        self._stack.setCurrentIndex(self._last_utility_index)

    def _update_landing_session_state(self):
        """Sync the landing page Return button with the current session state."""
        tab_name = _TABS[self._last_utility_index]["label"] if self._has_active_session else ""
        self._landing.set_has_active_session(self._has_active_session, tab_name)

    # ── Tab switching ──────────────────────────────────────────────────────────

    def _switch_tab(self, idx: int):
        """Switch the visible tab, update the hero strip, and repaint the pill buttons."""
        self._tab_idx = idx
        self._last_utility_index = idx
        self._stack.setCurrentIndex(idx)
        tab = _TABS[idx]
        self._hero_eyebrow.setText(tab["eyebrow"])
        self._hero_title.setText(tab["title"])
        self._hero_subtitle.setText(tab["subtitle"])
        self._repaint_pills()
        if self._has_active_session:
            self._update_landing_session_state()

    def _repaint_pills(self):
        """Rebuild the tab pill stylesheets — active pill is red-filled, inactive is outlined."""
        for i, btn in enumerate(self._tab_btns):
            if i == self._tab_idx:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {KS_RED};
                        color: {TEXT_WHITE};
                        border: none;
                        border-radius: 4px;
                        padding: 5px 14px;
                        font-family: 'Segoe UI';
                        font-size: 12px;
                        font-weight: 600;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent;
                        color: #9CA3AF;
                        border: 1px solid #374151;
                        border-radius: 4px;
                        padding: 5px 14px;
                        font-family: 'Segoe UI';
                        font-size: 12px;
                    }}
                    QPushButton:hover {{ color: {TEXT_WHITE}; border-color: {LOG_CMD}; }}
                """)

    # ── Status / CWD refresh ───────────────────────────────────────────────────

    def _on_status_changed(self, text: str, color: str):
        """Mirror the LogDrawer's status (text + dot colour) in the status bar,
        e.g. green "Ready", amber "Running…", red "Failed"."""
        self._status_lbl.setText(text)
        self._status_dot.setStyleSheet(
            f"color: {color}; font-size: 9px; background: transparent;")

    def _refresh_cwd(self):
        """
        Sync all three CWD display labels to the current working directory.

        Called every 2 seconds by _cwd_timer.  The tab widgets may call
        os.chdir() when the user browses for a case root, so we poll here
        rather than relying on a signal to keep the display current.
        """
        cwd = os.getcwd()
        basename = os.path.basename(cwd) or cwd
        self._cwd_lbl.setText(basename)   # header bar: short name only
        self._hero_cwd.setText(cwd)       # hero strip: full path badge
        self._sb_cwd.setText(cwd)         # status bar: full path (right-aligned)

        has_mesh = os.path.isfile(os.path.join(cwd, "constant", "polyMesh", "points"))
        self._paraview_btn.setEnabled(has_mesh)
        self._paraview_btn.setToolTip(
            "Open the current case in ParaView to inspect the mesh.\n"
            "ParaView must be installed on Windows."
            if has_mesh else
            "No mesh yet — run Background Mesh (and Snappy Hex Mesh) first.")

    # ── Open ParaView ──────────────────────────────────────────────────────────

    def _open_paraview(self):
        """
        Launch ParaView with the case's .foam file.

        ParaView runs on the Windows side, so the WSL path must be converted
        to a Windows-format UNC path using 'wslpath -w' before passing it to
        the executable.  If no .foam file exists yet, an empty one is created
        (ParaView only needs the file to exist — it reads the mesh from the
        surrounding case directories, not from the file contents).
        """
        cwd = os.getcwd()
        foam_files = [f for f in os.listdir(cwd) if f.endswith(".foam")]
        if not foam_files:
            # Create an empty sentinel file so ParaView can locate the case root.
            case_name = os.path.basename(cwd)
            foam_path = os.path.join(cwd, f"{case_name}.foam")
            open(foam_path, "w").close()
            foam_files = [os.path.basename(foam_path)]
            self._log.write(f"[ParaView] Created: {foam_path}\n", "info")

        foam_file = os.path.join(cwd, foam_files[0])
        pv_exe = find_paraview_exe()
        if not pv_exe:
            self._log.write(
                "[ParaView] ParaView not found. Install it under "
                "C:\\Program Files\\ParaView*\n", "error")
            return

        try:
            result = subprocess.run(
                ["wslpath", "-w", foam_file],
                capture_output=True, text=True)
            win_path = result.stdout.strip() if result.returncode == 0 else foam_file
        except Exception:
            win_path = foam_file

        self._log.write(f"[ParaView] Opening: {win_path}\n", "info")
        try:
            subprocess.Popen(
                [pv_exe, win_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            self._log.write(f"[ParaView] Failed to launch: {exc}\n", "error")

    # ── Window icon ────────────────────────────────────────────────────────────

    def _set_window_icon(self):
        """Apply the app icon (taskbar + title bar) if the .ico file shipped
        with the app is present; silently skip otherwise."""
        icon_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "icons", "openfoam_ui.ico"
        )
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

    # ── Center on screen ───────────────────────────────────────────────────────

    def _center(self):
        """Move the window to the centre of the primary screen."""
        screen = QApplication.primaryScreen().availableGeometry()
        frame  = self.frameGeometry()
        frame.moveCenter(screen.center())
        self.move(frame.topLeft())


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    """Create the QApplication, apply the shared tooltip style app-wide, show
    the main window, and signal the launcher that the GUI is up."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE_TOOLTIP)
    win = MainWindow()
    win.show()

    # Touch a ready sentinel on the first event-loop iteration — after Qt
    # has processed the show event and mapped the window.  The launcher
    # watches for this file so it can close its splash the instant the GUI
    # is actually visible, rather than waiting for a fixed timeout.
    def _signal_ready():
        try:
            with open('/tmp/openfoam_ui_ready', 'w') as f:
                f.write('ok')
        except Exception:
            pass

    QTimer.singleShot(0, _signal_ready)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
