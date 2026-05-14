#!/usr/bin/env python3
"""
ui_log_drawer.py — Collapsible, resizable log drawer pinned at the bottom.

The drawer sits between the main content stack and the status bar.  It has
two interaction modes:

  • Click the chevron button   — animate between collapsed (36 px) and a
                                 default expanded height (350 px).
  • Drag the bottom grip strip — resize freely between 36 px and 900 px.
                                 Drag upward to expand, downward to shrink.

Thread safety
-------------
Worker threads must NOT call Qt widget methods directly.  LogDrawer.write()
is the only public entry point for log text; it emits the internal signal
_append_sig which Qt automatically delivers to the main thread via a queued
connection because the signal crosses a thread boundary.  The actual text
insertion (_on_append) therefore always runs on the main thread.
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QPlainTextEdit, QSizePolicy, QFrame,
                              QApplication)
from PyQt5.QtCore import (Qt, QTimer, QPropertyAnimation, QEasingCurve,
                           pyqtSignal)
from PyQt5.QtGui import QColor, QTextCharFormat, QTextCursor

from ui_shared import (LOG_BG, LOG_FG, LOG_ERROR, LOG_WARN, LOG_INFO, LOG_CMD,
                        TEXT_MUTED, BORDER)

COLLAPSED_H = 36
EXPANDED_H  = 650
MAX_H       = 900


class _ResizeGrip(QWidget):
    """
    Thin (8 px) horizontal strip at the very top of the LogDrawer.

    Dragging this strip calls drag_cb(delta) where delta is positive when the
    mouse moves downward and negative when it moves upward.  _on_grip_drag
    subtracts delta from the current height so dragging the upper border
    upward (negative delta) increases the drawer's height.

    Positioned above the header so the user grabs the upper border and drags
    it upward to reveal more log output.
    """

    def __init__(self, drag_cb, parent=None):
        super().__init__(parent)
        self._drag_cb = drag_cb
        self._dragging = False
        self._last_y   = 0
        self.setFixedHeight(8)
        self.setCursor(Qt.SizeVerCursor)   # show vertical resize cursor on hover
        self.setStyleSheet(f"""
            QWidget {{
                background: #2D3748;
                border-bottom: 1px solid #374151;
            }}
            QWidget:hover {{ background: #4B5563; }}
        """)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._dragging = True
            self._last_y   = ev.globalPos().y()
        ev.accept()   # accept so Qt doesn't propagate upward

    def mouseMoveEvent(self, ev):
        if self._dragging:
            # delta > 0 when mouse moves down, < 0 when mouse moves up.
            # _on_grip_drag subtracts this, so dragging the upper border
            # upward (negative delta) correctly increases the drawer height.
            delta        = ev.globalPos().y() - self._last_y
            self._last_y = ev.globalPos().y()
            self._drag_cb(delta)
        ev.accept()

    def mouseReleaseEvent(self, ev):
        self._dragging = False
        ev.accept()


class LogDrawer(QWidget):
    """
    Collapsible, resizable log panel that sits above the status bar.

    Public API
    ----------
    write(message, tag)  — append coloured text; safe to call from any thread
    set_running(bool)    — start/stop the amber blinking dot animation

    Signals
    -------
    status_changed(text, colour)
        Emitted when a worker reports a status change.  The main window
        connects this to the status bar so the bar always reflects the latest
        worker state.

    _append_sig (internal)
        Private signal used only to move log text from worker threads to the
        main thread safely.  Do not connect to this from outside this class.
    """

    status_changed = pyqtSignal(str, str)   # (text, dot_colour) → status bar
    _append_sig    = pyqtSignal(str, str)   # internal: thread-safe text append

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded    = False
        self._line_count  = 0
        self._blink_state = False
        self._target_h    = EXPANDED_H   # persists the user's last expanded height

        self.setFixedHeight(COLLAPSED_H)
        self.setStyleSheet(f"background: {LOG_BG};")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._anim = QPropertyAnimation(self, b"maximumHeight")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.InOutQuad)
        self._anim.finished.connect(self._on_anim_finished)

        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._do_blink)

        self._build()
        self._append_sig.connect(self._on_append)

    # ── Build ──────────────────────────────────────────────────────────────────

    def _build(self):
        main_vbox = QVBoxLayout(self)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.setSpacing(0)

        # ── Resize grip (draggable upper border) ──────────────────────────────
        self._grip = _ResizeGrip(self._on_grip_drag)
        main_vbox.addWidget(self._grip)

        # ── Header strip (always visible) ─────────────────────────────────────
        hdr = QWidget()
        hdr.setFixedHeight(COLLAPSED_H)
        hdr.setStyleSheet(f"background: {LOG_BG};")
        hdr_row = QHBoxLayout(hdr)
        hdr_row.setContentsMargins(12, 0, 12, 0)
        hdr_row.setSpacing(8)

        self._dot_lbl = QLabel("●")
        self._dot_lbl.setStyleSheet(
            "color: #22C55E; font-size: 10px; border: none; background: transparent;")
        hdr_row.addWidget(self._dot_lbl)

        log_lbl = QLabel("OUTPUT LOG")
        log_lbl.setStyleSheet(
            f"color: {LOG_FG}; font-family: Consolas; font-size: 12px;"
            " font-weight: bold; border: none; background: transparent;")
        hdr_row.addWidget(log_lbl)

        self._count_lbl = QLabel("0 lines")
        self._count_lbl.setStyleSheet(
            f"color: {LOG_CMD}; font-family: Consolas; font-size: 12px;"
            " border: none; background: transparent;")
        hdr_row.addWidget(self._count_lbl)

        hdr_row.addStretch()

        _btn_style = f"""
            QPushButton {{
                color: {LOG_CMD};
                background: transparent;
                border: 1px solid #374151;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 11px;
                font-family: 'Segoe UI';
            }}
            QPushButton:hover {{ color: {LOG_FG}; border-color: {LOG_CMD}; }}
        """

        self._copy_btn = QPushButton("Copy")
        self._copy_btn.setStyleSheet(_btn_style)
        self._copy_btn.setVisible(False)
        self._copy_btn.clicked.connect(self._copy_log)
        hdr_row.addWidget(self._copy_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setStyleSheet(_btn_style)
        self._clear_btn.setVisible(False)
        self._clear_btn.clicked.connect(self._clear)
        hdr_row.addWidget(self._clear_btn)

        self._chevron_btn = QPushButton("▲")
        self._chevron_btn.setStyleSheet(f"""
            QPushButton {{
                color: {LOG_CMD};
                background: transparent;
                border: none;
                font-size: 12px;
                padding: 0 4px;
            }}
            QPushButton:hover {{ color: {LOG_FG}; }}
        """)
        self._chevron_btn.clicked.connect(self._toggle)
        hdr_row.addWidget(self._chevron_btn)

        main_vbox.addWidget(hdr)

        # ── Text area (visible when expanded) ─────────────────────────────────
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setStyleSheet(f"""
            QPlainTextEdit {{
                background: {LOG_BG};
                color: {LOG_FG};
                border: none;
                border-top: 1px solid #2D3748;
                font-family: Consolas;
                font-size: 13px;
                padding: 8px;
            }}
        """)
        self._text.setVisible(False)
        main_vbox.addWidget(self._text)

    # ── Public API ─────────────────────────────────────────────────────────────

    def write(self, message: str, tag: str = "") -> None:
        """
        Append a message to the log.  Safe to call from any thread.

        Qt's signal-slot mechanism automatically queues the call across the
        thread boundary, so the actual widget update always happens on the
        main thread even when called from a QThread worker.

        tag : one of "error", "warn", "info", "cmd", or "" (default colour)
        """
        self._append_sig.emit(message, tag)

    def set_running(self, running: bool) -> None:
        """
        Control the animated status dot in the header strip.

        True  → amber blinking dot (500 ms interval) — a job is running
        False → solid green dot — idle or job finished
        """
        if running:
            self._blink_timer.start(500)
        else:
            self._blink_timer.stop()
            self._dot_lbl.setStyleSheet(
                "color: #22C55E; font-size: 9px; border: none; background: transparent;")

    # ── Internal slots ─────────────────────────────────────────────────────────

    def _on_append(self, message: str, tag: str):
        """
        Slot connected to _append_sig; always runs on the main thread.

        Moves the cursor to the end of the document, applies a coloured
        QTextCharFormat, and inserts the message.  ensureCursorVisible()
        auto-scrolls to the newest line.
        """
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        colour_map = {
            "error": LOG_ERROR,
            "warn":  LOG_WARN,
            "info":  LOG_INFO,
            "cmd":   LOG_CMD,
        }
        fmt.setForeground(QColor(colour_map.get(tag, LOG_FG)))
        cursor.setCharFormat(fmt)
        cursor.insertText(message)
        self._text.setTextCursor(cursor)
        self._text.ensureCursorVisible()

        self._line_count += message.count("\n")
        self._count_lbl.setText(f"{self._line_count} lines")
        if self._expanded and self._line_count > 0:
            self._copy_btn.setVisible(True)
            self._clear_btn.setVisible(True)

    def _on_grip_drag(self, delta: int):
        """
        Resize the drawer in response to the user dragging the top grip strip.

        delta is positive when the mouse moves down and negative when it moves
        up (see _ResizeGrip.mouseMoveEvent).  We subtract it so that dragging
        the upper border upward (negative delta) increases the drawer height.
        setFixedHeight pins both min and max to the same value so the layout
        shrinks the content stack above the drawer rather than the window.
        """
        new_h = max(COLLAPSED_H, min(MAX_H, self.height() - delta))
        self.setFixedHeight(new_h)
        if new_h > COLLAPSED_H:
            self._target_h = new_h   # remember for chevron re-expand
            if not self._expanded:
                self._expanded = True
                self._text.setVisible(True)
                self._chevron_btn.setText("▼")
                self._copy_btn.setVisible(self._line_count > 0)
                self._clear_btn.setVisible(self._line_count > 0)
        else:
            if self._expanded:
                self._expanded = False
                self._text.setVisible(False)
                self._chevron_btn.setText("▲")
                self._copy_btn.setVisible(False)
                self._clear_btn.setVisible(False)

    def _toggle(self):
        """
        Animate the drawer between collapsed and expanded states.

        The QPropertyAnimation targets maximumHeight only, so we must reset
        minimumHeight before collapsing (otherwise the widget refuses to shrink
        below its current minimum) and set it to COLLAPSED_H before expanding
        (so the drawer never shrinks below its header height during the animation).
        """
        if self._expanded:
            self._expanded = False
            self._chevron_btn.setText("▲")
            self._copy_btn.setVisible(False)
            self._clear_btn.setVisible(False)
            self.setMinimumHeight(0)
            self.setMaximumHeight(MAX_H)
            self._anim.stop()
            self._anim.setStartValue(self.height())
            self._anim.setEndValue(COLLAPSED_H)
            self._anim.start()
        else:
            self._expanded = True
            self._chevron_btn.setText("▼")
            self._text.setVisible(True)
            self._copy_btn.setVisible(self._line_count > 0)
            self._clear_btn.setVisible(self._line_count > 0)
            self.setMinimumHeight(COLLAPSED_H)
            self.setMaximumHeight(MAX_H)
            self._anim.stop()
            self._anim.setStartValue(self.height())
            self._anim.setEndValue(self._target_h)
            self._anim.start()

    def _on_anim_finished(self):
        if not self._expanded:
            self._text.setVisible(False)
            self.setFixedHeight(COLLAPSED_H)

    def _clear(self):
        self._text.clear()
        self._line_count = 0
        self._count_lbl.setText("0 lines")
        self._copy_btn.setVisible(False)
        self._clear_btn.setVisible(False)

    def _copy_log(self):
        text = self._text.toPlainText()
        if not text:
            return
        QApplication.clipboard().setText(text)
        self._copy_btn.setText("✓ Copied")
        self._copy_btn.setEnabled(False)
        QTimer.singleShot(2000, self._reset_copy_btn)

    def _reset_copy_btn(self):
        self._copy_btn.setText("Copy")
        self._copy_btn.setEnabled(True)

    def _do_blink(self):
        self._blink_state = not self._blink_state
        color = "#F59E0B" if self._blink_state else "#92400E"
        self._dot_lbl.setStyleSheet(
            f"color: {color}; font-size: 9px; border: none; background: transparent;")
