#!/usr/bin/env python3
"""
Filename:    openfoam_ui.py
Author:      [placeholder]
Date:        2026-04-23
Description: Unified tkinter GUI for OpenFOAM mesh utilities.
             Tab 1 wraps generateBackgroundMesh.py via subprocess.
             Tab 2 re-implements generateSnappyHexMeshDict.py logic
             directly, using foamDictionary subprocess calls.

Dependencies:
    python3-tk   (sudo apt-get install python3-tk)

Launch (from an OpenFOAM case directory with the environment sourced):
    python3 /mnt/c/OpenFOAM/01_utilities/openfoam_ui.py
"""

import os
import sys
import queue
import shlex
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR       = os.path.dirname(os.path.abspath(__file__))
GENERATE_BG_MESH = os.path.join(SCRIPT_DIR, "generateBackgroundMesh.py")

# Keysight colour palette
KS_RED       = "#E90029"       # Keysight brand red — primary actions, header accents
KS_RED_DARK  = "#B8001F"       # Hover / pressed state for red buttons
KS_RED_LT    = "#FDE8EC"       # Light red tint — focus backgrounds
KS_BLACK     = "#1A1A1A"       # Header bar, dark surfaces
KS_CHARCOAL  = "#2D2D2D"       # Log panel background
BG_APP       = "#F4F4F4"       # App background — light gray
BG_CARD      = "#FFFFFF"       # Card background — white
BORDER       = "#CECECE"       # Default border — medium gray
BORDER_FOCUS = "#E90029"       # Focus ring — red
TEXT_PRIMARY = "#1A1A1A"       # Primary text — near black
TEXT_MUTED   = "#6B6B6B"       # Secondary label text — gray
TEXT_WHITE   = "#FFFFFF"       # White text on dark backgrounds
STATUS_RUN   = "#B45309"       # Running indicator — amber (unchanged)
STATUS_DONE  = "#166534"       # Done — green (unchanged)
STATUS_ERR   = "#991B1B"       # Error — dark red (unchanged)

STATUS_IDLE    = ("Ready",             "#475569")
STATUS_RUNNING = ("Running...",        STATUS_RUN)
STATUS_DONE_S  = ("Done",              STATUS_DONE)
STATUS_ERROR   = ("Error — check log", STATUS_ERR)

BOUNDARY_TYPES = ["wall", "patch", "faceZone"]
PLURAL_MAP     = {"wall": "walls", "patch": "patches", "faceZone": "faceZones"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_paraview_exe():
    """
    Scan C:/Program Files (WSL: /mnt/c/Program Files) for any ParaView installation.
    Returns the WSL path to paraview.exe, or None if not found.
    Picks the lexicographically last match so the newest version wins.
    """
    import glob
    pattern = "/mnt/c/Program Files/ParaView*/bin/paraview.exe"
    matches = sorted(glob.glob(pattern))
    return matches[-1] if matches else None


def positive_float(value):
    try:
        v = float(value)
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def get_stl_zone_names(path):
    """Return list of solid names from an ASCII STL file."""
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


def make_card(parent, title=None, pady_inner=14):
    """White card with optional bold title above it."""
    outer = tk.Frame(parent, bg=BG_APP)
    outer.pack(fill=tk.X, padx=20, pady=(0, 14))
    if title:
        tk.Label(outer, text=title, bg=BG_APP,
                 fg=KS_RED, font=("Segoe UI", 10, "bold")).pack(
            anchor="w", pady=(0, 6))
    inner = tk.Frame(outer, bg=BG_CARD,
                     highlightbackground=BORDER, highlightthickness=1)
    inner.pack(fill=tk.X)
    body = tk.Frame(inner, bg=BG_CARD)
    body.pack(fill=tk.X, padx=18, pady=pady_inner)
    return body


# ---------------------------------------------------------------------------
# LogPanel
# ---------------------------------------------------------------------------

class LogPanel(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=BG_APP, **kw)
        self._q = queue.Queue()

        toolbar = tk.Frame(self, bg=BG_APP)
        toolbar.pack(fill=tk.X, padx=4, pady=(4, 0))
        ttk.Button(toolbar, text="Clear log", style="D.TButton",
                   command=self.clear).pack(side=tk.RIGHT)

        text_frame = tk.Frame(self, bg=KS_CHARCOAL,
                              highlightbackground=BORDER, highlightthickness=1)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.text = tk.Text(
            text_frame, wrap=tk.WORD, bg=KS_CHARCOAL, fg="#E2E8F0",
            font=("Consolas", 9), state=tk.DISABLED, relief=tk.FLAT,
            insertbackground=TEXT_WHITE, padx=10, pady=8,
        )
        vsb = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text.yview)
        self.text.configure(yscrollcommand=vsb.set)
        self.text.tag_configure("error", foreground="#FCA5A5")
        self.text.tag_configure("warn",  foreground="#FCD34D")
        self.text.tag_configure("info",  foreground="#93C5FD")
        self.text.tag_configure("cmd",   foreground="#64748B")

        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._poll()

    def _poll(self):
        try:
            while True:
                msg, tag = self._q.get_nowait()
                self.text.configure(state=tk.NORMAL)
                self.text.insert(tk.END, msg, tag)
                self.text.see(tk.END)
                self.text.configure(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.after(50, self._poll)

    def write(self, msg, tag=""):
        self._q.put((msg, tag))

    def clear(self):
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.configure(state=tk.DISABLED)


# ---------------------------------------------------------------------------
# StatusBar
# ---------------------------------------------------------------------------

class StatusBar(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=KS_BLACK, height=30, **kw)
        self.pack_propagate(False)
        self._blink_after = None
        self._blink_state = False

        self._dot_canvas = tk.Canvas(self, bg=KS_BLACK, width=14, height=14,
                                     highlightthickness=0)
        self._dot_canvas.pack(side=tk.LEFT, padx=(10, 4), pady=8)
        self._dot_oval = self._dot_canvas.create_oval(2, 2, 12, 12,
                                                       fill="#475569", outline="")

        self._label = tk.Label(self, text="Ready", bg=KS_BLACK, fg=TEXT_WHITE,
                               font=("Segoe UI", 9))
        self._label.pack(side=tk.LEFT, pady=4)

        self._cwd_label = tk.Label(self, text="", bg=KS_BLACK, fg="#64748B",
                                   font=("Segoe UI", 8))
        self._cwd_label.pack(side=tk.RIGHT, padx=10)
        self._update_cwd()

    def _update_cwd(self):
        cwd = os.getcwd()
        if len(cwd) > 60:
            cwd = "…" + cwd[-59:]
        self._cwd_label.configure(text=cwd)
        self.after(2000, self._update_cwd)

    def set(self, status):
        text, color = status
        if self._blink_after is not None:
            self.after_cancel(self._blink_after)
            self._blink_after = None
        self._dot_canvas.itemconfig(self._dot_oval, fill=color)
        self._label.configure(text=text, fg=TEXT_WHITE)
        if text == "Running...":
            self._blink()

    def _blink(self):
        self._blink_state = not self._blink_state
        c = KS_RED if self._blink_state else STATUS_RUN
        self._dot_canvas.itemconfig(self._dot_oval, fill=c)
        self._blink_after = self.after(600, self._blink)


# ---------------------------------------------------------------------------
# Tab 1 -- Background Mesh
# ---------------------------------------------------------------------------

class BackgroundMeshTab(tk.Frame):
    def __init__(self, parent, log: LogPanel, status: StatusBar, **kw):
        kw.setdefault("bg", BG_APP)
        super().__init__(parent, **kw)
        self._log     = log
        self._status  = status
        self._running = False
        self._build()

    def _build(self):
        tk.Frame(self, bg=BG_APP, height=16).pack()

        # STL file card
        stl_body = make_card(self, "STL file")
        stl_row = tk.Frame(stl_body, bg=BG_CARD)
        stl_row.pack(fill=tk.X)
        tk.Label(stl_row, text="Path:", bg=BG_CARD, fg=TEXT_MUTED,
                 font=("Segoe UI", 9), width=6, anchor="e").pack(side=tk.LEFT)
        self._stl = tk.StringVar()
        ttk.Entry(stl_row, textvariable=self._stl, width=52).pack(
            side=tk.LEFT, padx=(0, 8), fill=tk.X, expand=True)
        ttk.Button(stl_row, text="Browse…", style="S.TButton",
                   command=self._browse).pack(side=tk.LEFT)
        self._stl_err = tk.Label(stl_body, text="", fg=STATUS_ERR,
                                  font=("Segoe UI", 8), bg=BG_CARD)
        self._stl_err.pack(anchor="w", pady=(2, 0))

        # Grid resolution card
        grid_body = make_card(self, "Grid resolution")
        self._d_vars = {}
        self._d_errs = {}
        for name in ("dx", "dy", "dz"):
            row = tk.Frame(grid_body, bg=BG_CARD)
            row.pack(fill=tk.X, pady=5)
            tk.Label(row, text=f"{name}:", bg=BG_CARD, fg=TEXT_MUTED,
                     font=("Segoe UI", 9), width=6, anchor="e").pack(side=tk.LEFT)
            v = tk.StringVar()
            ttk.Entry(row, textvariable=v, width=14).pack(side=tk.LEFT, padx=(0, 8))
            err = tk.Label(row, text="", fg=STATUS_ERR,
                           font=("Segoe UI", 8), bg=BG_CARD)
            err.pack(side=tk.LEFT)
            self._d_vars[name] = v
            self._d_errs[name] = err

        # Action row (right-aligned, no card)
        btn_row = tk.Frame(self, bg=BG_APP)
        btn_row.pack(fill=tk.X, padx=20, pady=8)
        self._run_btn = ttk.Button(btn_row, text="Generate Background Mesh",
                                    style="P.TButton", command=self._run)
        self._run_btn.pack(side=tk.RIGHT)

    def _browse(self):
        p = filedialog.askopenfilename(
            title="Select STL file",
            filetypes=[("STL files", "*.stl"), ("All files", "*.*")])
        if p:
            self._stl.set(p)

    def _validate(self):
        ok = True
        self._stl_err.configure(text="")
        for e in self._d_errs.values():
            e.configure(text="")

        stl = self._stl.get().strip()
        if not stl:
            self._stl_err.configure(text="Required"); ok = False
        elif not os.path.isfile(stl):
            self._stl_err.configure(text="File not found"); ok = False

        for name in ("dx", "dy", "dz"):
            v = self._d_vars[name].get().strip()
            if not v:
                self._d_errs[name].configure(text="Required"); ok = False
            elif positive_float(v) is None:
                self._d_errs[name].configure(text="Must be a positive number"); ok = False
        return ok

    def _run(self):
        if self._running or not self._validate():
            return
        self._running = True
        self._run_btn.configure(state=tk.DISABLED)
        self._status.set(STATUS_RUNNING)
        self._log.write("\n[Background Mesh] Starting...\n", "info")

        OF_BASHRC = "/usr/lib/openfoam/openfoam2506/etc/bashrc"
        args_str = " ".join([
            shlex.quote(sys.executable), shlex.quote(GENERATE_BG_MESH),
            "-stlPath", shlex.quote(self._stl.get().strip()),
            "-dx",      self._d_vars["dx"].get().strip(),
            "-dy",      self._d_vars["dy"].get().strip(),
            "-dz",      self._d_vars["dz"].get().strip(),
        ])
        bash_cmd = f"source {OF_BASHRC} && {args_str}"
        cmd = ["bash", "-c", bash_cmd]

        def worker():
            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, cwd=os.getcwd())
                for line in proc.stdout:
                    tag = "error" if any(
                        w in line.lower() for w in ("error", "failed")) else ""
                    self._log.write(line, tag)
                proc.wait()
                if proc.returncode == 0:
                    cwd = os.getcwd()
                    case_name = os.path.basename(cwd)
                    foam_path = os.path.join(cwd, f"{case_name}.foam")
                    open(foam_path, "w").close()
                    self._log.write(f"[Background Mesh] Created: {foam_path}\n", "info")
                    self._log.write("[Background Mesh] Done.\n", "info")
                    self.after(0, lambda: self._status.set(STATUS_DONE_S))
                else:
                    self._log.write(
                        f"[Background Mesh] Exited with code {proc.returncode}\n", "error")
                    self.after(0, lambda: self._status.set(STATUS_ERROR))
            except Exception as exc:
                self._log.write(f"[Background Mesh] Exception: {exc}\n", "error")
                self.after(0, lambda: self._status.set(STATUS_ERROR))
            finally:
                self._running = False
                self.after(0, lambda: self._run_btn.configure(state=tk.NORMAL))

        threading.Thread(target=worker, daemon=True).start()


# ---------------------------------------------------------------------------
# Tab 2 -- SnappyHexMesh Dict
# ---------------------------------------------------------------------------

class SnappyHexMeshTab(tk.Frame):

    def __init__(self, parent, log: LogPanel, status: StatusBar, **kw):
        kw.setdefault("bg", BG_APP)
        super().__init__(parent, **kw)
        self._log    = log
        self._status = status
        self._cwd    = tk.StringVar(value=os.getcwd())

        self._surface_files         = []
        self._edge_files            = []
        self._shapes                = []
        self._geometry_region_names = []
        self._region_zone_list      = []
        self._special_region_names  = []
        self._combined_region_names = []
        self._layer_surfaces        = []
        self._add_layers            = False
        self._snap_explicit         = False

        self._edge_ref_vars    = {}
        self._vol_ref_vars     = {}
        self._vol_ref_lvl_vars = {}
        self._gap_ref_vars     = {}
        self._gap_fields       = {}
        self._surf_ref_data    = {}
        self._layer_patch_vars = {}
        self._ncbl_var         = tk.IntVar(value=2)
        self._loc_x = self._loc_y = self._loc_z = tk.StringVar()

        self._build_ui()

    # ------------------------------------------------------------------ layout

    def _build_ui(self):
        # Working directory slim card
        top_outer = tk.Frame(self, bg=BG_APP)
        top_outer.pack(fill=tk.X, padx=20, pady=(12, 8))
        top_inner = tk.Frame(top_outer, bg=BG_CARD,
                             highlightbackground=BORDER, highlightthickness=1)
        top_inner.pack(fill=tk.X)
        top_body = tk.Frame(top_inner, bg=BG_CARD)
        top_body.pack(fill=tk.X, padx=14, pady=6)
        tk.Label(top_body, text="Working directory:", bg=BG_CARD,
                 fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        tk.Label(top_body, textvariable=self._cwd, bg=BG_CARD,
                 fg=TEXT_MUTED, font=("Consolas", 9)).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(top_body, text="Change…", style="S.TButton",
                   command=self._change_cwd).pack(side=tk.RIGHT)

        # Scrollable canvas
        scroll_outer = tk.Frame(self, bg=BG_APP)
        scroll_outer.pack(fill=tk.BOTH, expand=True)

        vsb = ttk.Scrollbar(scroll_outer, orient=tk.VERTICAL)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas = tk.Canvas(scroll_outer, yscrollcommand=vsb.set,
                                  bd=0, highlightthickness=0, bg=BG_APP)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.configure(command=self._canvas.yview)

        self._inner = tk.Frame(self._canvas, bg=BG_APP)
        self._win_id = self._canvas.create_window(
            (0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>",
                         lambda _e: self._canvas.configure(
                             scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
                          lambda e: self._canvas.itemconfig(
                              self._win_id, width=e.width))
        self._canvas.bind_all("<MouseWheel>",
                              lambda e: self._canvas.yview_scroll(
                                  int(-1 * (e.delta / 120)), "units"))

        # Instruction banner
        banner = tk.Frame(self._inner, bg="#FFF8E1",
                          highlightbackground="#F0C040", highlightthickness=1)
        banner.pack(fill=tk.X, padx=20, pady=(8, 4))
        tk.Label(banner,
                 text='Start by selecting your geometry files in Section 1, then click "Apply geometry".',
                 bg="#FFF8E1", fg="#7A5C00", font=("Segoe UI", 9),
                 padx=12, pady=6).pack(anchor="w")

        self._build_sec1()
        self._build_sec2()
        self._build_sec3()
        self._build_sec4()
        self._build_sec5()
        for sec_outer in [self._sec1_outer, self._sec2_outer, self._sec3_outer,
                          self._sec4_outer, self._sec5_outer]:
            sec_outer.pack(fill=tk.X, padx=20, pady=(0, 14))

    def _change_cwd(self):
        d = filedialog.askdirectory(title="Select OpenFOAM case directory",
                                    initialdir=self._cwd.get())
        if d:
            self._cwd.set(d)
            os.chdir(d)

    def _scroll_bottom(self):
        self._canvas.update_idletasks()
        self._canvas.yview_moveto(1.0)

    # ------------------------------------------------------------------ card helpers

    def _section_card(self, title):
        """Create an unpacked section card inside self._inner. Returns (outer, body)."""
        outer = tk.Frame(self._inner, bg=BG_APP)
        tk.Label(outer, text=title, bg=BG_APP,
                 fg=KS_RED, font=("Segoe UI", 10, "bold")).pack(
            anchor="w", pady=(0, 6))
        inner_frame = tk.Frame(outer, bg=BG_CARD,
                               highlightbackground=BORDER, highlightthickness=1)
        inner_frame.pack(fill=tk.X)
        body = tk.Frame(inner_frame, bg=BG_CARD)
        body.pack(fill=tk.X, padx=18, pady=14)
        return outer, body

    def _sub_card(self, parent, title):
        """Inline labelled sub-card inside a section body."""
        outer = tk.Frame(parent, bg=BG_APP)
        outer.pack(fill=tk.X, pady=2)
        tk.Label(outer, text=title, bg=BG_APP, fg=KS_RED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        inner_frame = tk.Frame(outer, bg=BG_CARD,
                               highlightbackground=BORDER, highlightthickness=1)
        inner_frame.pack(fill=tk.X)
        body = tk.Frame(inner_frame, bg=BG_CARD)
        body.pack(fill=tk.X, padx=10, pady=6)
        return body

    # ---------------------------------------------------------------- section 1

    def _build_sec1(self):
        self._sec1_outer, sec1 = self._section_card("Geometry files")
        # Packed by the loop in _build_ui — do not pack here

        tk.Label(sec1,
                 text="Files found in constant/triSurface/ — tick Surface or Edge for each:",
                 bg=BG_CARD, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 6))

        self._file_list_frame = tk.Frame(sec1, bg=BG_CARD)
        self._file_list_frame.pack(fill=tk.X, pady=(0, 4))
        self._file_rows = []

        ttk.Button(sec1, text="Refresh file list", style="S.TButton",
                   command=self._refresh_file_list).pack(anchor="w", pady=(0, 8))

        sf = tk.Frame(sec1, bg=BG_CARD)
        sf.pack(fill=tk.X, pady=(0, 4))
        tk.Label(sf, text="Additional standard shapes:",
                 bg=BG_CARD, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self._num_shapes_var = tk.IntVar(value=0)
        sp = ttk.Spinbox(sf, from_=0, to=20, textvariable=self._num_shapes_var,
                         width=5, command=self._refresh_shape_fields)
        sp.pack(side=tk.LEFT, padx=8)
        sp.bind("<Return>",   lambda _e: self._refresh_shape_fields())
        sp.bind("<FocusOut>", lambda _e: self._refresh_shape_fields())

        self._shapes_container = tk.Frame(sec1, bg=BG_CARD)
        self._shapes_container.pack(fill=tk.X)
        self._shape_widgets = []

        self._sec1_err = tk.Label(sec1, text="", fg=STATUS_ERR,
                                   font=("Segoe UI", 8), bg=BG_CARD)
        self._sec1_err.pack(pady=(4, 0))
        ttk.Button(sec1, text="Apply geometry →",
                   style="P.TButton", command=self._apply_sec1).pack(
            side=tk.RIGHT, pady=(8, 0))

        self._refresh_file_list()

    def _refresh_file_list(self):
        for w in self._file_list_frame.winfo_children():
            w.destroy()
        self._file_rows.clear()

        tri_dir = os.path.join(self._cwd.get(), "constant", "triSurface")
        if not os.path.isdir(tri_dir):
            tk.Label(self._file_list_frame,
                     text=f"  Not found: {tri_dir}", fg=STATUS_ERR,
                     bg=BG_CARD, font=("Segoe UI", 9)).pack(anchor="w")
            return

        files = sorted(f for f in os.listdir(tri_dir)
                       if os.path.isfile(os.path.join(tri_dir, f)))
        if not files:
            tk.Label(self._file_list_frame,
                     text="  No files found", fg=STATUS_RUN,
                     bg=BG_CARD, font=("Segoe UI", 9)).pack(anchor="w")
            return

        hdr = tk.Frame(self._file_list_frame, bg="#EEF2F8", height=28)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(hdr, text="Filename", width=42, anchor="w",
                 bg="#EEF2F8", fg=KS_RED,
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=6)
        tk.Label(hdr, text="Surface", width=9, anchor="center",
                 bg="#EEF2F8", fg=KS_RED,
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        tk.Label(hdr, text="Edge", width=9, anchor="center",
                 bg="#EEF2F8", fg=KS_RED,
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)

        for i, fname in enumerate(files):
            row_bg = BG_CARD if i % 2 == 0 else "#F8FAFC"
            row = tk.Frame(self._file_list_frame, bg=row_bg, height=28)
            row.pack(fill=tk.X)
            row.pack_propagate(False)
            tk.Label(row, text=fname, width=42, anchor="w",
                     bg=row_bg, font=("Consolas", 9),
                     fg=TEXT_PRIMARY).pack(side=tk.LEFT, padx=6)
            sv, ev = tk.BooleanVar(), tk.BooleanVar()
            ttk.Checkbutton(row, variable=sv).pack(side=tk.LEFT, padx=18)
            ttk.Checkbutton(row, variable=ev).pack(side=tk.LEFT, padx=12)
            self._file_rows.append((fname, sv, ev))

    def _refresh_shape_fields(self):
        for w in self._shapes_container.winfo_children():
            w.destroy()
        self._shape_widgets.clear()

        try:
            n = int(self._num_shapes_var.get())
        except (ValueError, tk.TclError):
            return

        for i in range(n):
            s_outer = tk.Frame(self._shapes_container, bg=BG_APP)
            s_outer.pack(fill=tk.X, pady=4)
            tk.Label(s_outer, text=f"Shape {i+1}", bg=BG_APP,
                     fg=KS_RED, font=("Segoe UI", 9, "bold")).pack(anchor="w")
            s_inner = tk.Frame(s_outer, bg=BG_CARD,
                               highlightbackground=BORDER, highlightthickness=1)
            s_inner.pack(fill=tk.X)
            frm = tk.Frame(s_inner, bg=BG_CARD)
            frm.pack(fill=tk.X, padx=12, pady=8)

            type_var = tk.StringVar(value="Box")
            tr = tk.Frame(frm, bg=BG_CARD)
            tr.pack(fill=tk.X, pady=(0, 6))
            tk.Label(tr, text="Type:", bg=BG_CARD, fg=TEXT_MUTED,
                     font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 8))
            cb = ttk.Combobox(tr, textvariable=type_var, state="readonly",
                               values=["Box", "Cylinder", "Sphere"], width=12)
            cb.pack(side=tk.LEFT)
            flds = tk.Frame(frm, bg=BG_CARD)
            flds.pack(fill=tk.X)
            sd = {"type_var": type_var, "fields_frame": flds, "widgets": {}}
            self._shape_widgets.append(sd)
            cb.bind("<<ComboboxSelected>>",
                    lambda _e, d=sd: self._rebuild_shape_fields(d))
            self._rebuild_shape_fields(sd)

    def _rebuild_shape_fields(self, sd):
        for w in sd["fields_frame"].winfo_children():
            w.destroy()
        sd["widgets"].clear()
        f, w = sd["fields_frame"], sd["widgets"]
        t = sd["type_var"].get()

        def xyz(label, row):
            tk.Label(f, text=label, bg=BG_CARD, fg=TEXT_MUTED,
                     font=("Segoe UI", 9)).grid(row=row, column=0, sticky="e", padx=4)
            vx, vy, vz = tk.StringVar(), tk.StringVar(), tk.StringVar()
            ttk.Entry(f, textvariable=vx, width=10).grid(row=row, column=1, padx=2)
            ttk.Entry(f, textvariable=vy, width=10).grid(row=row, column=2, padx=2)
            ttk.Entry(f, textvariable=vz, width=10).grid(row=row, column=3, padx=2)
            tk.Label(f, text="x   y   z", fg=TEXT_MUTED, bg=BG_CARD,
                     font=("Segoe UI", 7)).grid(row=row+1, column=1, columnspan=3, sticky="w")
            return vx, vy, vz

        def scalar(label, row):
            tk.Label(f, text=label, bg=BG_CARD, fg=TEXT_MUTED,
                     font=("Segoe UI", 9)).grid(row=row, column=0, sticky="e", padx=4)
            rv = tk.StringVar()
            ttk.Entry(f, textvariable=rv, width=12).grid(row=row, column=1, padx=2)
            return rv

        if t == "Box":
            w["min_x"], w["min_y"], w["min_z"] = xyz("Min point:", 0)
            w["max_x"], w["max_y"], w["max_z"] = xyz("Max point:", 2)
        elif t == "Cylinder":
            w["p1_x"], w["p1_y"], w["p1_z"] = xyz("Point 1 (axis start):", 0)
            w["outer_r1"] = scalar("Outer radius 1:", 2)
            w["inner_r1"] = scalar("Inner radius 1:", 3)
            w["p2_x"], w["p2_y"], w["p2_z"] = xyz("Point 2 (axis end):", 4)
            w["outer_r2"] = scalar("Outer radius 2:", 6)
            w["inner_r2"] = scalar("Inner radius 2:", 7)
        elif t == "Sphere":
            w["cx"], w["cy"], w["cz"] = xyz("Centre:", 0)
            w["radius"] = scalar("Radius:", 2)

    def _apply_sec1(self):
        self._sec1_err.configure(text="")
        surf = [fn for fn, sv, ev in self._file_rows if sv.get()]
        edge = [fn for fn, sv, ev in self._file_rows if ev.get()]

        overlap = set(surf) & set(edge)
        if overlap:
            self._sec1_err.configure(
                text=f"Cannot be both Surface and Edge: {', '.join(overlap)}")
            return
        if not surf and not edge:
            self._sec1_err.configure(text="Select at least one file.")
            return

        shapes = []
        for i, sd in enumerate(self._shape_widgets):
            t  = sd["type_var"].get()
            sw = sd["widgets"]
            sh = {"name": f"shape_{i+1}", "type": t}
            try:
                if t == "Box":
                    sh["min"] = (float(sw["min_x"].get()), float(sw["min_y"].get()), float(sw["min_z"].get()))
                    sh["max"] = (float(sw["max_x"].get()), float(sw["max_y"].get()), float(sw["max_z"].get()))
                elif t == "Cylinder":
                    sh["p1"]       = (float(sw["p1_x"].get()), float(sw["p1_y"].get()), float(sw["p1_z"].get()))
                    sh["outer_r1"] = float(sw["outer_r1"].get())
                    sh["inner_r1"] = float(sw["inner_r1"].get())
                    sh["p2"]       = (float(sw["p2_x"].get()), float(sw["p2_y"].get()), float(sw["p2_z"].get()))
                    sh["outer_r2"] = float(sw["outer_r2"].get())
                    sh["inner_r2"] = float(sw["inner_r2"].get())
                elif t == "Sphere":
                    sh["centre"] = (float(sw["cx"].get()), float(sw["cy"].get()), float(sw["cz"].get()))
                    sh["radius"] = float(sw["radius"].get())
            except ValueError:
                self._sec1_err.configure(text=f"Shape {i+1}: invalid numeric field")
                return
            shapes.append(sh)

        tri_dir = os.path.join(self._cwd.get(), "constant", "triSurface")
        zone_list = []
        for sf in surf:
            zones = get_stl_zone_names(os.path.join(tri_dir, sf))
            zone_list.append(zones)

        self._surface_files         = surf
        self._edge_files            = edge
        self._shapes                = shapes
        self._region_zone_list      = zone_list
        self._geometry_region_names = [os.path.splitext(f)[0] for f in surf]
        self._special_region_names  = [s["name"] for s in shapes]
        self._combined_region_names = self._geometry_region_names + self._special_region_names

        self._populate_sec2()
        self._populate_sec3()
        self._populate_sec4()
        self._scroll_bottom()

    # ---------------------------------------------------------------- section 2

    def _build_sec2(self):
        self._sec2_outer, self._sec2_body = self._section_card("Castellation & refinement")
        tk.Label(self._sec2_body,
                 text="Select geometry files above and click 'Apply geometry' to populate this section.",
                 fg=TEXT_MUTED, bg=BG_CARD, font=("Segoe UI", 9),
                 wraplength=600).pack(pady=12)

    def _populate_sec2(self):
        for w in self._sec2_body.winfo_children():
            w.destroy()
        self._edge_ref_vars.clear()
        self._vol_ref_vars.clear()
        self._vol_ref_lvl_vars.clear()
        self._gap_ref_vars.clear()
        self._gap_fields.clear()
        self._surf_ref_data.clear()

        body = self._sec2_body

        def sec_label(text):
            tk.Label(body, text=text, bg=BG_CARD, fg=KS_RED,
                     font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(8, 2))

        # -- Feature edge refinement ------------------------------------------
        if self._edge_files:
            sec_label("Feature edge refinement levels")
            for ef in self._edge_files:
                row = tk.Frame(body, bg=BG_CARD)
                row.pack(fill=tk.X, pady=1)
                tk.Label(row, text=f"  {ef}", width=38, anchor="w",
                         bg=BG_CARD, fg=TEXT_PRIMARY,
                         font=("Consolas", 9)).pack(side=tk.LEFT)
                v = tk.IntVar(value=1)
                ttk.Spinbox(row, from_=0, to=20, textvariable=v, width=5).pack(side=tk.LEFT)
                self._edge_ref_vars[ef] = v

        # -- Volume refinement ------------------------------------------------
        sec_label("Volume refinement")
        tk.Label(body, text="Check regions requiring non-zero refinement:",
                 bg=BG_CARD, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(anchor="w")
        for reg in self._combined_region_names:
            row = tk.Frame(body, bg=BG_CARD)
            row.pack(fill=tk.X, pady=1)
            cb_v  = tk.BooleanVar(value=False)
            lvl_v = tk.IntVar(value=1)
            ttk.Checkbutton(row, text=reg, variable=cb_v, width=32).pack(side=tk.LEFT)
            tk.Label(row, text="Level:", bg=BG_CARD, fg=TEXT_MUTED,
                     font=("Segoe UI", 9)).pack(side=tk.LEFT)
            ttk.Spinbox(row, from_=0, to=20, textvariable=lvl_v, width=5).pack(
                side=tk.LEFT, padx=2)
            self._vol_ref_vars[reg]     = cb_v
            self._vol_ref_lvl_vars[reg] = lvl_v

        # -- Gap refinement ---------------------------------------------------
        sec_label("Gap refinement")
        for reg in self._geometry_region_names:
            grp = self._sub_card(body, reg)
            gap_v = tk.BooleanVar(value=False)
            ttk.Checkbutton(grp, text="Enable gap refinement",
                            variable=gap_v).pack(anchor="w")
            d = tk.Frame(grp, bg=BG_CARD)
            d.pack(fill=tk.X)
            nc_v, ls_v, mr_v = tk.IntVar(value=3), tk.IntVar(value=0), tk.IntVar(value=3)
            for row_i, (lbl, var) in enumerate([
                ("Min cells between surfaces:", nc_v),
                ("Start level:",               ls_v),
                ("Max refinement level:",       mr_v),
            ]):
                tk.Label(d, text=lbl, bg=BG_CARD, fg=TEXT_MUTED,
                         font=("Segoe UI", 9)).grid(row=row_i, column=0, sticky="e", padx=4)
                ttk.Spinbox(d, from_=0, to=20, textvariable=var, width=6)\
                    .grid(row=row_i, column=1, sticky="w")
            self._gap_ref_vars[reg] = gap_v
            self._gap_fields[reg]   = {"num_cells": nc_v, "level_start": ls_v, "max_ref": mr_v}

        # -- Surface refinement -----------------------------------------------
        sec_label("Surface refinement")

        standalone = []
        for ii, reg in enumerate(self._geometry_region_names):
            if len(self._region_zone_list[ii]) <= 1:
                standalone.append(reg)
        standalone.extend(self._special_region_names)

        for ii, reg in enumerate(self._geometry_region_names):
            zone_names = self._region_zone_list[ii]
            grp = self._sub_card(body, reg)

            if len(zone_names) > 1:
                rd = {"multi_zone": True, "zone_names": zone_names}
                gl = tk.Frame(grp, bg=BG_CARD)
                gl.pack(fill=tk.X)
                gmin_v, gmax_v = tk.IntVar(value=0), tk.IntVar(value=1)
                tk.Label(gl, text="Global min level:", bg=BG_CARD, fg=TEXT_MUTED,
                         font=("Segoe UI", 9)).pack(side=tk.LEFT)
                ttk.Spinbox(gl, from_=0, to=20, textvariable=gmin_v, width=5)\
                    .pack(side=tk.LEFT, padx=2)
                tk.Label(gl, text="  Global max level:", bg=BG_CARD, fg=TEXT_MUTED,
                         font=("Segoe UI", 9)).pack(side=tk.LEFT)
                ttk.Spinbox(gl, from_=0, to=20, textvariable=gmax_v, width=5)\
                    .pack(side=tk.LEFT, padx=2)
                rd["global_min"], rd["global_max"] = gmin_v, gmax_v
                rd["zones"] = {}
                for zn in zone_names:
                    zg = self._sub_card(grp, f"Zone: {zn}")
                    zmin_v, zmax_v = tk.IntVar(value=0), tk.IntVar(value=1)
                    bt_v  = tk.StringVar(value="wall")
                    cz_v  = tk.BooleanVar(value=False)
                    czn_v = tk.StringVar(value="")
                    zr = tk.Frame(zg, bg=BG_CARD)
                    zr.pack(fill=tk.X)
                    tk.Label(zr, text="Min:", bg=BG_CARD, fg=TEXT_MUTED,
                             font=("Segoe UI", 9)).pack(side=tk.LEFT)
                    ttk.Spinbox(zr, from_=0, to=20, textvariable=zmin_v, width=5)\
                        .pack(side=tk.LEFT, padx=2)
                    tk.Label(zr, text="  Max:", bg=BG_CARD, fg=TEXT_MUTED,
                             font=("Segoe UI", 9)).pack(side=tk.LEFT)
                    ttk.Spinbox(zr, from_=0, to=20, textvariable=zmax_v, width=5)\
                        .pack(side=tk.LEFT, padx=2)
                    tk.Label(zr, text="  Type:", bg=BG_CARD, fg=TEXT_MUTED,
                             font=("Segoe UI", 9)).pack(side=tk.LEFT)
                    ttk.Combobox(zr, textvariable=bt_v, values=BOUNDARY_TYPES,
                                 state="readonly", width=10).pack(side=tk.LEFT, padx=2)
                    czr = tk.Frame(zg, bg=BG_CARD)
                    czr.pack(fill=tk.X)
                    ttk.Checkbutton(czr, text="Enclose cellZone?",
                                    variable=cz_v).pack(side=tk.LEFT)
                    ttk.Entry(czr, textvariable=czn_v, width=20).pack(side=tk.LEFT, padx=4)
                    tk.Label(czr, text="(cellZone name)", fg=TEXT_MUTED,
                             bg=BG_CARD, font=("Segoe UI", 7)).pack(side=tk.LEFT)
                    rd["zones"][zn] = {
                        "min": zmin_v, "max": zmax_v,
                        "btype": bt_v, "cell_zone": cz_v, "cz_name": czn_v,
                    }
                self._surf_ref_data[reg] = rd
            # single-zone handled in the standalone loop below

        for reg in standalone:
            if reg in self._surf_ref_data:
                continue
            grp = self._sub_card(body, reg)
            rd = {"multi_zone": False}
            def_v  = tk.BooleanVar(value=False)
            smin_v = tk.IntVar(value=0)
            smax_v = tk.IntVar(value=1)
            bt_v   = tk.StringVar(value="wall")
            cz_v   = tk.BooleanVar(value=False)
            czn_v  = tk.StringVar(value="")
            ttk.Checkbutton(grp,
                            text="Define surface refinement / patch type for this region?",
                            variable=def_v).pack(anchor="w")
            sr = tk.Frame(grp, bg=BG_CARD)
            sr.pack(fill=tk.X)
            tk.Label(sr, text="Min level:", bg=BG_CARD, fg=TEXT_MUTED,
                     font=("Segoe UI", 9)).pack(side=tk.LEFT)
            ttk.Spinbox(sr, from_=0, to=20, textvariable=smin_v, width=5)\
                .pack(side=tk.LEFT, padx=2)
            tk.Label(sr, text="  Max level:", bg=BG_CARD, fg=TEXT_MUTED,
                     font=("Segoe UI", 9)).pack(side=tk.LEFT)
            ttk.Spinbox(sr, from_=0, to=20, textvariable=smax_v, width=5)\
                .pack(side=tk.LEFT, padx=2)
            tk.Label(sr, text="  Type:", bg=BG_CARD, fg=TEXT_MUTED,
                     font=("Segoe UI", 9)).pack(side=tk.LEFT)
            ttk.Combobox(sr, textvariable=bt_v, values=BOUNDARY_TYPES,
                         state="readonly", width=10).pack(side=tk.LEFT, padx=2)
            czr = tk.Frame(grp, bg=BG_CARD)
            czr.pack(fill=tk.X)
            ttk.Checkbutton(czr, text="Enclose cellZone?",
                            variable=cz_v).pack(side=tk.LEFT)
            ttk.Entry(czr, textvariable=czn_v, width=20).pack(side=tk.LEFT, padx=4)
            tk.Label(czr, text="(cellZone name)", fg=TEXT_MUTED,
                     bg=BG_CARD, font=("Segoe UI", 7)).pack(side=tk.LEFT)
            rd.update({"define": def_v, "min": smin_v, "max": smax_v,
                       "btype": bt_v, "cell_zone": cz_v, "cz_name": czn_v})
            self._surf_ref_data[reg] = rd

        # -- nCellsBetweenLevels + locationInMesh ----------------------------
        tk.Frame(body, bg=BORDER, height=1).pack(fill=tk.X, pady=10)

        ncbl_row = tk.Frame(body, bg=BG_CARD)
        ncbl_row.pack(fill=tk.X)
        tk.Label(ncbl_row,
                 text="Cells between mesh levels  (1 = fast transition, 2 = balanced, 3 = robust):",
                 bg=BG_CARD, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self._ncbl_var = tk.IntVar(value=2)
        ttk.Spinbox(ncbl_row, from_=1, to=3, textvariable=self._ncbl_var, width=4)\
            .pack(side=tk.LEFT, padx=6)

        loc_row = tk.Frame(body, bg=BG_CARD)
        loc_row.pack(fill=tk.X, pady=(6, 2))
        tk.Label(loc_row, text="Location in mesh (point inside the region to keep):  x",
                 bg=BG_CARD, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self._loc_x = tk.StringVar()
        self._loc_y = tk.StringVar()
        self._loc_z = tk.StringVar()
        for lbl, v in [("", self._loc_x), ("  y", self._loc_y), ("  z", self._loc_z)]:
            if lbl:
                tk.Label(loc_row, text=lbl, bg=BG_CARD, fg=TEXT_MUTED,
                         font=("Segoe UI", 9)).pack(side=tk.LEFT)
            ttk.Entry(loc_row, textvariable=v, width=10).pack(side=tk.LEFT, padx=2)

        self._sec2_err = tk.Label(body, text="", fg=STATUS_ERR,
                                   font=("Segoe UI", 8), bg=BG_CARD)
        self._sec2_err.pack()

    def _apply_sec2(self):
        pass

    # ---------------------------------------------------------------- section 3

    def _build_sec3(self):
        self._sec3_outer, self._sec3_body = self._section_card("Snap controls")
        tk.Label(self._sec3_body,
                 text="Select geometry files above and click 'Apply geometry' to populate this section.",
                 fg=TEXT_MUTED, bg=BG_CARD, font=("Segoe UI", 9),
                 wraplength=600).pack(pady=12)

    def _populate_sec3(self):
        for w in self._sec3_body.winfo_children():
            w.destroy()
        self._snap_type_var = tk.StringVar(value="Implicit")
        tk.Label(self._sec3_body, text="Feature snapping type:",
                 bg=BG_CARD, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 4))
        ttk.Radiobutton(self._sec3_body, text="Implicit (no edge files needed)",
                        variable=self._snap_type_var, value="Implicit").pack(anchor="w")
        ttk.Radiobutton(self._sec3_body, text="Explicit (uses selected edge files)",
                        variable=self._snap_type_var, value="Explicit").pack(anchor="w")
        if not self._edge_files:
            tk.Label(self._sec3_body,
                     text="  WARNING: No edge files selected — Explicit will fall back to Implicit.",
                     fg=STATUS_RUN, bg=BG_CARD, font=("Segoe UI", 8)).pack(anchor="w")

    def _apply_sec3(self):
        if hasattr(self, "_snap_type_var") and \
                self._snap_type_var.get() == "Explicit" and not self._edge_files:
            messagebox.showwarning(
                "No Edge Files",
                "Explicit snapping selected but no edge files were chosen.\n"
                "Falling back to Implicit feature snapping.")
            self._snap_type_var.set("Implicit")
        self._snap_explicit = (
            self._snap_type_var.get() == "Explicit"
            if hasattr(self, "_snap_type_var") else False
        )

    # ---------------------------------------------------------------- section 4

    def _build_sec4(self):
        self._sec4_outer, self._sec4_body = self._section_card("Layer addition")
        tk.Label(self._sec4_body,
                 text="Select geometry files above and click 'Apply geometry' to populate this section.",
                 fg=TEXT_MUTED, bg=BG_CARD, font=("Segoe UI", 9),
                 wraplength=600).pack(pady=12)

    def _populate_sec4(self):
        for w in self._sec4_body.winfo_children():
            w.destroy()
        self._layer_patch_vars.clear()

        self._add_layers_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self._sec4_body, text="Add boundary layers?",
                        variable=self._add_layers_var,
                        command=self._toggle_layer_details).pack(anchor="w")

        self._layer_details = tk.Frame(self._sec4_body, bg=BG_CARD)
        self._layer_details.pack(fill=tk.X)

        self._layer_surfaces = self._compute_layer_surfaces()

        if self._layer_surfaces:
            tk.Label(self._layer_details,
                     text="Patches available for layer addition:",
                     bg=BG_CARD, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 2))
            for patch in self._layer_surfaces:
                row = tk.Frame(self._layer_details, bg=BG_CARD)
                row.pack(fill=tk.X, pady=1)
                add_v = tk.BooleanVar(value=False)
                num_v = tk.IntVar(value=3)
                ttk.Checkbutton(row, text=patch, variable=add_v, width=32).pack(side=tk.LEFT)
                tk.Label(row, text="Layers:", bg=BG_CARD, fg=TEXT_MUTED,
                         font=("Segoe UI", 9)).pack(side=tk.LEFT)
                ttk.Spinbox(row, from_=1, to=50, textvariable=num_v, width=5)\
                    .pack(side=tk.LEFT, padx=2)
                self._layer_patch_vars[patch] = (add_v, num_v)
        else:
            tk.Label(self._layer_details,
                     text="  (No patches derived from Section 2 surface definitions)",
                     fg=TEXT_MUTED, bg=BG_CARD, font=("Segoe UI", 9)).pack(anchor="w")

        self._layer_details.pack_forget()   # hidden until checkbox ticked

    def _compute_layer_surfaces(self):
        surfaces = []
        standalone = []
        for ii, reg in enumerate(self._geometry_region_names):
            if len(self._region_zone_list[ii]) > 1:
                for zn in self._region_zone_list[ii]:
                    surfaces.append(zn)
            else:
                standalone.append(reg)
        standalone.extend(self._special_region_names)

        for reg in standalone:
            rd = self._surf_ref_data.get(reg, {})
            if rd.get("define") and rd["define"].get():
                btype = rd["btype"].get()
                if btype in ("wall", "patch"):
                    surfaces.append(reg)
                elif btype == "faceZone":
                    surfaces.append(reg)
                    surfaces.append(reg + "_slave")
        return surfaces

    def _toggle_layer_details(self):
        if self._add_layers_var.get():
            self._layer_details.pack(fill=tk.X)
        else:
            self._layer_details.pack_forget()

    def _apply_sec4(self):
        self._add_layers = (
            self._add_layers_var.get() if hasattr(self, "_add_layers_var") else False
        )

    # ---------------------------------------------------------------- section 5

    def _build_sec5(self):
        self._sec5_outer, sec5 = self._section_card("Generate")
        tk.Label(sec5,
                 text="Generates system/snappyHexMeshDict (and fvSchemes, fvSolution if layers enabled).",
                 bg=BG_CARD, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(anchor="w")
        self._gen_btn = ttk.Button(sec5, text="Generate snappyHexMeshDict",
                                    style="P.TButton", command=self._generate)
        self._gen_btn.pack(side=tk.RIGHT, pady=(12, 0))

    # --------------------------------------------------------- generation logic

    def _generate(self):
        cwd         = self._cwd.get()
        sys_dir     = os.path.join(cwd, "system")
        ctrl_dict   = os.path.join(sys_dir, "controlDict")
        snappy_dict = os.path.join(sys_dir, "snappyHexMeshDict")

        if not os.path.isfile(ctrl_dict):
            messagebox.showerror("Missing controlDict",
                "system/controlDict not found.\n"
                "Run this tool from an OpenFOAM case directory.")
            return
        if os.path.isfile(snappy_dict):
            if not messagebox.askyesno("Overwrite?",
                "system/snappyHexMeshDict already exists.\nOverwrite it?"):
                return

        # Validate locationInMesh floats
        try:
            float(self._loc_x.get())
            float(self._loc_y.get())
            float(self._loc_z.get())
        except (ValueError, AttributeError):
            messagebox.showerror("Invalid input",
                "Location in mesh: enter three valid numbers (x, y, z).")
            return

        # Resolve snap type — default to Implicit if sec3 was never populated
        if not hasattr(self, "_snap_type_var"):
            self._snap_explicit = False
        else:
            self._snap_explicit = (self._snap_type_var.get() == "Explicit")

        # Collect layer state fresh at generation time
        self._add_layers     = self._add_layers_var.get() if hasattr(self, "_add_layers_var") else False
        self._layer_surfaces = self._compute_layer_surfaces()

        self._gen_btn.configure(state=tk.DISABLED)
        self._status.set(STATUS_RUNNING)
        self._log.write("\n[snappyHexMeshDict] Generating...\n", "info")

        def worker():
            try:
                self._do_generate(sys_dir, snappy_dict, cwd)
                self._log.write("[snappyHexMeshDict] Done.\n", "info")
                self.after(0, lambda: self._status.set(STATUS_DONE_S))
            except Exception as exc:
                self._log.write(f"[snappyHexMeshDict] Error: {exc}\n", "error")
                self.after(0, lambda: self._status.set(STATUS_ERROR))
            finally:
                self.after(0, lambda: self._gen_btn.configure(state=tk.NORMAL))

        threading.Thread(target=worker, daemon=True).start()

    def _fcmd(self, cmd_str, cwd):
        """Run a foamDictionary (or any shell) command and stream to log."""
        self._log.write(f"  $ {cmd_str}\n", "cmd")
        try:
            bash_cmd = f"source /usr/lib/openfoam/openfoam2506/etc/bashrc && {cmd_str}"
            r = subprocess.run(["bash", "-c", bash_cmd], text=True,
                               capture_output=True, cwd=cwd)
            if r.stdout:
                self._log.write(r.stdout)
            if r.returncode != 0 and r.stderr:
                self._log.write(r.stderr, "error")
        except Exception as exc:
            self._log.write(f"  Exception: {exc}\n", "error")

    def _do_generate(self, sys_dir, snappy_dict, cwd):
        C = lambda s: self._fcmd(s, cwd)   # noqa: E731

        # -- Initial file ------------------------------------------------------
        header = (
            "/*--------------------------------*- C++ -*----------------------------------*\\\n"
            "| =========                 |                                                 |\n"
            "| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |\n"
            "|  \\\\    /   O peration     | Version:  v2312                                 |\n"
            "|   \\\\  /    A nd           | Website:  www.openfoam.com                      |\n"
            "|    \\\\/     M anipulation  |                                                 |\n"
            "\\*---------------------------------------------------------------------------*/\n"
            "FoamFile\n{\n"
            "\tversion     2.0;\n"
            "\tformat      ascii;\n"
            "\tclass       dictionary;\n"
            "\tobject      snappyHexMeshDict;\n"
            "}\n"
            "// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n\n"
        )
        with open(snappy_dict, "w") as fh:
            fh.write(header)

        C("foamDictionary system/snappyHexMeshDict -entry castellatedMesh -add true")
        C("foamDictionary system/snappyHexMeshDict -entry snap -add true")
        C("foamDictionary system/snappyHexMeshDict -entry addLayers -add false")
        C('foamDictionary system/snappyHexMeshDict -entry geometry -add "{}"')
        C('foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls -add "{}"')
        C('foamDictionary system/snappyHexMeshDict -entry snapControls -add "{}"')
        C('foamDictionary system/snappyHexMeshDict -entry addLayersControls -add "{}"')
        C('foamDictionary system/snappyHexMeshDict -entry meshQualityControls -add "{}"')
        C("foamDictionary system/snappyHexMeshDict -entry mergeTolerance -add 1e-6")

        # -- Geometry section --------------------------------------------------
        tri_dir = os.path.join(cwd, "constant", "triSurface")
        for sf in self._surface_files:
            reg   = os.path.splitext(sf)[0]
            zones = get_stl_zone_names(os.path.join(tri_dir, sf))
            C(f'foamDictionary system/snappyHexMeshDict -entry geometry/{sf} -add "{{}}"')
            C(f"foamDictionary system/snappyHexMeshDict -entry geometry/{sf}/type -add triSurfaceMesh")
            C(f"foamDictionary system/snappyHexMeshDict -entry geometry/{sf}/name -add {reg}")
            if len(zones) > 1:
                C(f'foamDictionary system/snappyHexMeshDict -entry geometry/{sf}/regions -add "{{}}"')
                for zn in zones:
                    C(f'foamDictionary system/snappyHexMeshDict -entry geometry/{sf}/regions/{zn} -add "{{}}"')
                    C(f"foamDictionary system/snappyHexMeshDict -entry geometry/{sf}/regions/{zn}/name -add {zn}")

        for sh in self._shapes:
            n = sh["name"]
            C(f'foamDictionary system/snappyHexMeshDict -entry geometry/{n} -add "{{}}"')
            if sh["type"] == "Box":
                mn, mx = sh["min"], sh["max"]
                C(f"foamDictionary system/snappyHexMeshDict -entry geometry/{n}/type -add searchableBox")
                C(f'foamDictionary system/snappyHexMeshDict -entry geometry/{n}/min -add "({mn[0]} {mn[1]} {mn[2]})"')
                C(f'foamDictionary system/snappyHexMeshDict -entry geometry/{n}/max -add "({mx[0]} {mx[1]} {mx[2]})"')
            elif sh["type"] == "Cylinder":
                p1, p2 = sh["p1"], sh["p2"]
                C(f"foamDictionary system/snappyHexMeshDict -entry geometry/{n}/type -add searchableCone")
                C(f'foamDictionary system/snappyHexMeshDict -entry geometry/{n}/point1 -add "({p1[0]} {p1[1]} {p1[2]})"')
                C(f"foamDictionary system/snappyHexMeshDict -entry geometry/{n}/radius1 -add {sh['outer_r1']}")
                C(f"foamDictionary system/snappyHexMeshDict -entry geometry/{n}/innerRadius1 -add {sh['inner_r1']}")
                C(f'foamDictionary system/snappyHexMeshDict -entry geometry/{n}/point2 -add "({p2[0]} {p2[1]} {p2[2]})"')
                C(f"foamDictionary system/snappyHexMeshDict -entry geometry/{n}/radius2 -add {sh['outer_r2']}")
                C(f"foamDictionary system/snappyHexMeshDict -entry geometry/{n}/innerRadius2 -add {sh['inner_r2']}")
            elif sh["type"] == "Sphere":
                c = sh["centre"]
                C(f"foamDictionary system/snappyHexMeshDict -entry geometry/{n}/type -add searchableSphere")
                C(f'foamDictionary system/snappyHexMeshDict -entry geometry/{n}/centre -add "({c[0]} {c[1]} {c[2]})"')
                C(f"foamDictionary system/snappyHexMeshDict -entry geometry/{n}/radius -add {sh['radius']}")

        # -- castellatedMeshControls fixed entries -----------------------------
        C("foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/maxLocalCells -add 100000000")
        C("foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/maxGlobalCells -add 300000000")
        C("foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/minRefinementCells -add 10")
        C("foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/maxLoadUnbalance -add 0.1")

        # -- Features (edge refinement) -- injected by file edit ---------------
        with open(snappy_dict, "r") as fh:
            lines = fh.readlines()
        modified, inside = [], False
        for line in lines:
            stripped = line.strip()
            modified.append(line)
            if stripped.startswith("castellatedMeshControls"):
                inside = True
            if inside and stripped == "}":
                modified.insert(-1, "    features\n")
                modified.insert(-1, "    (\n")
                for ef in self._edge_files:
                    lvl = self._edge_ref_vars.get(ef, tk.IntVar(value=0)).get()
                    modified.insert(-1, "        {\n")
                    modified.insert(-1, f'        file    "{ef}";\n')
                    modified.insert(-1, f"        level    {lvl};\n")
                    modified.insert(-1, "        }\n")
                modified.insert(-1, "    );\n")
                inside = False
        with open(snappy_dict, "w") as fh:
            fh.writelines(modified)
        self._log.write("  [features block injected]\n")

        # -- Volume refinement -------------------------------------------------
        C('foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementRegions -add "{}"')
        for reg in self._combined_region_names:
            lvl = (self._vol_ref_lvl_vars[reg].get()
                   if self._vol_ref_vars.get(reg) and self._vol_ref_vars[reg].get() else 0)
            C(f'foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementRegions/{reg} -add "{{}}"')
            C(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementRegions/{reg}/mode -add inside")
            C(f'foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementRegions/{reg}/levels -add "((1.0 {lvl}))"')

        # -- Gap refinement ----------------------------------------------------
        for reg in self._geometry_region_names:
            if self._gap_ref_vars.get(reg) and self._gap_ref_vars[reg].get():
                gf = self._gap_fields[reg]
                nc = gf["num_cells"].get()
                ls = gf["level_start"].get()
                mr = gf["max_ref"].get()
                C(f'foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementRegions/{reg}/gapLevel -add "({nc} {ls} {mr})"')
                C(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementRegions/{reg}/gapMode -add mixed")

        # -- Surface refinement ------------------------------------------------
        C('foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces -add "{}"')

        layer_surfaces_gen = []   # track for layer addition

        for ii, reg in enumerate(self._geometry_region_names):
            zone_names = self._region_zone_list[ii]
            rd         = self._surf_ref_data.get(reg, {})

            if len(zone_names) > 1:
                gmin = rd["global_min"].get()
                gmax = rd["global_max"].get()
                C(f'foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{reg} -add "{{}}"')
                C(f'foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{reg}/level -add "({gmin} {gmax})"')
                C(f'foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{reg}/regions -add "{{}}"')
                for zn in zone_names:
                    zd    = rd["zones"][zn]
                    zmin  = zd["min"].get()
                    zmax  = zd["max"].get()
                    btype = zd["btype"].get()
                    plural = PLURAL_MAP[btype]
                    C(f'foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{reg}/regions/{zn} -add "{{}}"')
                    C(f'foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{reg}/regions/{zn}/level -add "({zmin} {zmax})"')
                    C(f'foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{reg}/regions/{zn}/patchInfo -add "{{}}"')
                    C(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{reg}/regions/{zn}/patchInfo/type -add {btype}")
                    C(f'foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{reg}/regions/{zn}/patchInfo/inGroups -add "({plural})"')
                    layer_surfaces_gen.append(zn)
            else:
                pass

        # standalone surfaces (single-zone STL + shapes)
        standalone = []
        for ii, reg in enumerate(self._geometry_region_names):
            if len(self._region_zone_list[ii]) <= 1:
                standalone.append(reg)
        standalone.extend(self._special_region_names)

        for reg in standalone:
            rd = self._surf_ref_data.get(reg, {})
            if not (rd.get("define") and rd["define"].get()):
                continue
            smin  = rd["min"].get()
            smax  = rd["max"].get()
            btype = rd["btype"].get()
            plural = PLURAL_MAP[btype]
            C(f'foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{reg} -add "{{}}"')
            C(f'foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{reg}/level -add "({smin} {smax})"')
            if btype in ("wall", "patch"):
                C(f'foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{reg}/patchInfo -add "{{}}"')
                C(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{reg}/patchInfo/type -add {btype}")
                C(f'foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{reg}/patchInfo/inGroups -add "({plural})"')
                layer_surfaces_gen.append(reg)
            elif btype == "faceZone":
                C(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{reg}/faceZone -add {reg}")
                C(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{reg}/faceType -add internal")
                if rd["cell_zone"].get():
                    czname = rd["cz_name"].get() or reg
                    C(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{reg}/cellZone -add {czname}")
                    C(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/refinementSurfaces/{reg}/cellZoneInside -add inside")
                layer_surfaces_gen.append(reg)
                layer_surfaces_gen.append(reg + "_slave")

        C("foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/resolveFeatureAngle -add 30")
        C(f"foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/nCellsBetweenLevels -add {self._ncbl_var.get()}")
        lx, ly, lz = self._loc_x.get(), self._loc_y.get(), self._loc_z.get()
        C(f'foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/locationInMesh -add "({lx} {ly} {lz})"')
        C("foamDictionary system/snappyHexMeshDict -entry castellatedMeshControls/allowFreeStandingZoneFaces -add true")

        # -- Snap controls -----------------------------------------------------
        C("foamDictionary system/snappyHexMeshDict -entry snapControls/nSmoothPatch -add 3")
        C("foamDictionary system/snappyHexMeshDict -entry snapControls/nSmoothInternal -add 5")
        C("foamDictionary system/snappyHexMeshDict -entry snapControls/tolerance -add 2.0")
        C("foamDictionary system/snappyHexMeshDict -entry snapControls/nSolveIter -add 30")
        C("foamDictionary system/snappyHexMeshDict -entry snapControls/nRelaxIter -add 5")
        C("foamDictionary system/snappyHexMeshDict -entry snapControls/nFeatureSnapIter -add 10")
        if self._snap_explicit:
            C("foamDictionary system/snappyHexMeshDict -entry snapControls/implicitFeatureSnap -add false")
            C("foamDictionary system/snappyHexMeshDict -entry snapControls/explicitFeatureSnap -add true")
            C("foamDictionary system/snappyHexMeshDict -entry snapControls/multiRegionFeatureSnap -add true")
        else:
            C("foamDictionary system/snappyHexMeshDict -entry snapControls/implicitFeatureSnap -add true")
            C("foamDictionary system/snappyHexMeshDict -entry snapControls/explicitFeatureSnap -add false")
            C("foamDictionary system/snappyHexMeshDict -entry snapControls/multiRegionFeatureSnap -add false")

        # -- Layer addition ----------------------------------------------------
        if self._add_layers:
            C("foamDictionary system/snappyHexMeshDict -entry addLayers -set true")
            for key, val in [
                ("relativeSizes",            "true"),
                ("minThickness",             "0.1"),
                ("featureAngle",             "120"),
                ("nGrow",                    "0"),
                ("maxFaceThicknessRatio",    "0.5"),
                ("nBufferCellsNoExtrude",    "0"),
                ("nLayerIter",               "50"),
                ("nSmoothThickness",         "10"),
                ("nRelaxIter",               "5"),
                ("nRelaxedIter",             "20"),
                ("nSmoothSurfaceNormals",    "1"),
                ("thicknessModel",           "finalAndExpansion"),
                ("finalLayerThickness",      "0.5"),
                ("expansionRatio",           "1.1"),
            ]:
                C(f"foamDictionary system/snappyHexMeshDict -entry addLayersControls/{key} -add {val}")
            C('foamDictionary system/snappyHexMeshDict -entry addLayersControls/layers -add "{}"')

            patch_list = "( "
            for patch in self._layer_surfaces:
                entry = self._layer_patch_vars.get(patch)
                if entry and entry[0].get():
                    num = entry[1].get()
                    patch_list += patch + " "
                    C(f'foamDictionary system/snappyHexMeshDict -entry addLayersControls/layers/{patch} -add "{{}}"')
                    C(f"foamDictionary system/snappyHexMeshDict -entry addLayersControls/layers/{patch}/nSurfaceLayers -add {num}")
            patch_list += ");"

            C("foamDictionary system/snappyHexMeshDict -entry addLayersControls/meshShrinker -add displacementMotionSolver")
            C("foamDictionary system/snappyHexMeshDict -entry addLayersControls/solver -add displacementLaplacian")
            txt = "{ diffusivity quadratic inverseDistance " + patch_list + " }"
            C(f'foamDictionary system/snappyHexMeshDict -entry addLayersControls/displacementLaplacianCoeffs -add "{txt}"')

            fv_schemes_content = """\
FoamFile
{
    version         2;
    format          ascii;
    class           dictionary;
    object          fvSchemes;
}

divSchemes
{

}

gradSchemes
{
    grad(cellDisplacement)  cellLimited leastSquares 1;

}

laplacianSchemes
{
    laplacian(diffusivity,cellDisplacement) Gauss linear limited corrected 0.5;
}

"""
            fv_solution_content = """\
FoamFile
{
    format      ascii;
    class       dictionary;
    object      fvSolution;
}

solvers
{
   cellDisplacement
   {
       solver          GAMG;
       smoother        GaussSeidel;
       minIter         1;
       tolerance       1e-7;
       relTol          0.01;
   }
}

"""
            sys_folder = os.path.join(cwd, "system")
            for fname, content in [("fvSchemes", fv_schemes_content),
                                    ("fvSolution", fv_solution_content)]:
                fpath = os.path.join(sys_folder, fname)
                with open(fpath, "w") as fh:
                    fh.write(content)
                self._log.write(f"  Written: {fpath}\n")

        # -- meshQualityControls -----------------------------------------------
        for key, val in [
            ("maxNonOrtho",          "65"),
            ("maxBoundarySkewness",  "20"),
            ("maxInternalSkewness",  "4"),
            ("maxConcave",           "80"),
            ("minFlatness",          "0.5"),
            ("minVol",               "1e-13"),
            ("minTetQuality",        "-1e-30"),
            ("minArea",              "-1"),
            ("minTwist",             "0.02"),
            ("minDeterminant",       "0.001"),
            ("minFaceWeight",        "0.05"),
            ("minVolRatio",          "0.01"),
            ("minTriangleTwist",     "-1"),
            ("minEdgeLength",        "-1"),
        ]:
            C(f"foamDictionary system/snappyHexMeshDict -entry meshQualityControls/{key} -add {val}")
        C('foamDictionary system/snappyHexMeshDict -entry meshQualityControls/relaxed -add "{}"')
        C("foamDictionary system/snappyHexMeshDict -entry meshQualityControls/relaxed/maxNonOrtho -add 70")
        C("foamDictionary system/snappyHexMeshDict -entry meshQualityControls/nSmoothScale -add 4")
        C("foamDictionary system/snappyHexMeshDict -entry meshQualityControls/errorReduction -add 0.75")

        self._log.write(f"  Written: {snappy_dict}\n", "info")


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OpenFOAM Mesh Utilities")
        self.geometry("1020x800")
        self.minsize(780, 580)
        self.configure(bg=BG_APP)
        self._apply_styles()
        self._build()

    def _apply_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("TFrame",       background=BG_APP)
        style.configure("TLabel",       background=BG_APP, foreground=TEXT_PRIMARY,
                        font=("Segoe UI", 10))
        style.configure("TCheckbutton", background=BG_CARD, foreground=TEXT_PRIMARY,
                        font=("Segoe UI", 10))
        style.configure("TRadiobutton", background=BG_CARD, foreground=TEXT_PRIMARY,
                        font=("Segoe UI", 10))

        style.configure("TEntry",       fieldbackground=BG_CARD, bordercolor=BORDER,
                        lightcolor=BORDER, darkcolor=BORDER, borderwidth=1,
                        font=("Segoe UI", 10), padding=5)
        style.map("TEntry",
                  bordercolor=[("focus", BORDER_FOCUS)],
                  lightcolor=[("focus", BORDER_FOCUS)])

        style.configure("TSpinbox",     fieldbackground=BG_CARD, bordercolor=BORDER,
                        arrowcolor=TEXT_MUTED, font=("Segoe UI", 10), padding=4)
        style.configure("TCombobox",    fieldbackground=BG_CARD, bordercolor=BORDER,
                        font=("Segoe UI", 10))

        style.configure("P.TButton",    background=KS_RED, foreground=TEXT_WHITE,
                        font=("Segoe UI", 10, "bold"), borderwidth=0,
                        padding=(18, 9), relief="flat")
        style.map("P.TButton",
                  background=[("active", KS_RED_DARK), ("disabled", BORDER)])

        style.configure("S.TButton",    background=BG_CARD, foreground=KS_RED,
                        font=("Segoe UI", 10), borderwidth=1,
                        relief="solid", padding=(14, 7))
        style.map("S.TButton",
                  background=[("active", KS_RED_LT)],
                  bordercolor=[("active", KS_RED)])

        style.configure("D.TButton",    background=BG_CARD, foreground=STATUS_ERR,
                        font=("Segoe UI", 9), borderwidth=1, relief="solid",
                        padding=(10, 5))

    def _build(self):
        # Header bar (52px, black)
        header = tk.Frame(self, bg=KS_BLACK, height=52)
        header.pack(side=tk.TOP, fill=tk.X)
        header.pack_propagate(False)

        left_side = tk.Frame(header, bg=KS_BLACK)
        left_side.pack(side=tk.LEFT, padx=16, pady=8)
        icon_c = tk.Canvas(left_side, width=16, height=16, bg=KS_BLACK,
                           highlightthickness=0)
        icon_c.pack(side=tk.LEFT, padx=(0, 10))
        icon_c.create_rectangle(1, 1, 15, 15, fill=KS_RED, outline="")
        tk.Label(left_side, text="OpenFOAM Mesh Utilities", bg=KS_BLACK, fg=TEXT_WHITE,
                 font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT)

        right_side = tk.Frame(header, bg=KS_BLACK)
        right_side.pack(side=tk.RIGHT, padx=16)

        btn1 = tk.Button(right_side, text="Background Mesh",
                         bg=KS_RED, fg=TEXT_WHITE,
                         font=("Segoe UI", 10), relief=tk.FLAT, padx=16, pady=6,
                         cursor="hand2", command=lambda: self._switch_tab(0))
        btn1.pack(side=tk.LEFT, padx=(0, 4))

        btn2 = tk.Button(right_side, text="SnappyHexMesh Dict",
                         bg=KS_BLACK, fg="#9A9A9A",
                         font=("Segoe UI", 10), relief=tk.FLAT, padx=16, pady=6,
                         cursor="hand2", command=lambda: self._switch_tab(1))
        btn2.pack(side=tk.LEFT)

        btn_pv = tk.Button(right_side, text="Open ParaView",
                           bg=KS_BLACK, fg="#9A9A9A",
                           font=("Segoe UI", 10), relief=tk.FLAT, padx=16, pady=6,
                           cursor="hand2", command=self._open_paraview)
        btn_pv.pack(side=tk.LEFT, padx=(16, 0))

        self._tab_btns = [btn1, btn2]

        # Status bar at very bottom
        self._status = StatusBar(self)
        self._status.pack(side=tk.BOTTOM, fill=tk.X)

        # PanedWindow: content on top, log panel below (resizable sash)
        paned = tk.PanedWindow(self, orient=tk.VERTICAL, sashrelief=tk.FLAT,
                                sashwidth=4, bg=BORDER)
        paned.pack(fill=tk.BOTH, expand=True)

        content_frame = tk.Frame(paned, bg=BG_APP)
        paned.add(content_frame, minsize=300)

        log_outer = tk.Frame(paned, bg=BG_APP)
        paned.add(log_outer, minsize=120)
        tk.Label(log_outer, text="Output log", bg=BG_APP, fg=KS_RED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8, pady=(6, 0))
        self._log = LogPanel(log_outer)
        self._log.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self.after(100, lambda: paned.sash_place(0, 0, 540))

        # Two tab frames placed on top of each other
        self._tab1 = BackgroundMeshTab(content_frame, self._log, self._status,
                                        bg=BG_APP)
        self._tab2 = SnappyHexMeshTab(content_frame, self._log, self._status,
                                       bg=BG_APP)
        self._tab1.place(relwidth=1, relheight=1)
        self._tab2.place(relwidth=1, relheight=1)
        self._tab1.tkraise()

    def _open_paraview(self):
        cwd = os.getcwd()
        foam_files = sorted(f for f in os.listdir(cwd) if f.endswith(".foam"))
        if not foam_files:
            messagebox.showwarning(
                "No .foam file found",
                f"No .foam file found in:\n{cwd}\n\nGenerate the background mesh first.")
            return

        foam_path = os.path.join(cwd, foam_files[0])
        try:
            win_path = subprocess.check_output(
                ["wslpath", "-w", foam_path], text=True).strip()
        except Exception:
            win_path = foam_path

        paraview_exe = _find_paraview_exe()

        if paraview_exe is None:
            manual = filedialog.askopenfilename(
                title="Locate paraview.exe",
                initialdir="/mnt/c/Program Files",
                filetypes=[("Executable", "paraview.exe"), ("All files", "*.*")])
            if not manual:
                return
            paraview_exe = manual
            self._log.write(f"[ParaView] Using manually selected: {paraview_exe}\n", "warn")
        else:
            self._log.write(f"[ParaView] Auto-detected: {paraview_exe}\n", "info")

        try:
            subprocess.Popen([paraview_exe, win_path])
        except Exception as exc:
            messagebox.showerror("ParaView launch failed", str(exc))
            self._log.write(f"[ParaView] Launch error: {exc}\n", "error")

    def _switch_tab(self, idx):
        [self._tab1, self._tab2][idx].tkraise()
        for i, btn in enumerate(self._tab_btns):
            if i == idx:
                btn.configure(bg=KS_RED, fg=TEXT_WHITE)
            else:
                btn.configure(bg=KS_BLACK, fg="#9A9A9A")


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
