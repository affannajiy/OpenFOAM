"""
openfoam_ui_launcher.py — Windows launcher for OpenFOAM Mesh Utilities GUI.

Runs pre-flight checks via WSL, then launches openfoam_ui.py inside WSL.
Stdlib only: tkinter, subprocess, sys, os, time.
"""
import tkinter as tk
from tkinter import messagebox
import subprocess
import sys
import os
import time

_CREATE_NO_WINDOW = 0x08000000
_WSL_EXE = 'wsl'
_FOAM_BASHRC_2506 = '/usr/lib/openfoam/openfoam2506/etc/bashrc'
_FOAM_BASHRC_2312 = '/usr/lib/openfoam/openfoam2312/etc/bashrc'
_REQUIRED_PACKAGES = ['PyQt5', 'numpy']


def windows_path_to_wsl(path):
    """Convert C:\\foo\\bar or C:/foo/bar to /mnt/c/foo/bar."""
    path = path.replace('\\', '/')
    if len(path) >= 2 and path[1] == ':':
        drive = path[0].lower()
        rest = path[2:]
        if rest and not rest.startswith('/'):
            rest = '/' + rest
        return f'/mnt/{drive}{rest}'
    return path


def _wsl(cmd, timeout=15):
    """Run a bash command inside WSL. Returns (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(
            [_WSL_EXE, 'bash', '-c', cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return -1, '', 'wsl.exe not found on PATH'
    except subprocess.TimeoutExpired:
        return -2, '', f'WSL command timed out after {timeout}s'
    except Exception as exc:
        return -3, '', str(exc)


def _get_exe_dir():
    """Return the directory containing the running .exe or .py."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _set_splash_icon(root):
    """Set the taskbar/title-bar icon from icons/icon_256.png if present."""
    icon_path = os.path.join(_get_exe_dir(), 'icons', 'icon_256.png')
    if os.path.exists(icon_path):
        try:
            img = tk.PhotoImage(file=icon_path)
            root.iconphoto(True, img)
            root._icon_img = img  # keep reference so GC doesn't collect it
        except Exception:
            pass


class _Splash:
    """Dark branded splash window. X button does nothing during pre-flight."""

    _BG = '#1A1A1A'
    _RED = '#E90029'
    _FG = '#FFFFFF'
    _FG_DIM = '#888888'
    _TRACK = '#2E2E2E'
    W, H = 500, 270

    def __init__(self):
        self.root = tk.Tk()
        _set_splash_icon(self.root)
        self.root.title('OpenFOAM Mesh Utilities')
        self.root.configure(bg=self._BG)
        self.root.resizable(False, False)
        self.root.protocol('WM_DELETE_WINDOW', lambda: None)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - self.W) // 2
        y = (sh - self.H) // 2
        self.root.geometry(f'{self.W}x{self.H}+{x}+{y}')

        self._build()
        self.root.update()

    def _build(self):
        tk.Frame(self.root, bg=self._RED, height=5).pack(fill='x')

        body = tk.Frame(self.root, bg=self._BG)
        body.pack(fill='both', expand=True, padx=36, pady=22)

        row = tk.Frame(body, bg=self._BG)
        row.pack(fill='x')

        # Try to show the app icon (64 px) next to the title
        self._splash_icon = None
        icon64_path = os.path.join(_get_exe_dir(), 'icons', 'icon_64.png')
        if os.path.exists(icon64_path):
            try:
                self._splash_icon = tk.PhotoImage(file=icon64_path)
                tk.Label(row, image=self._splash_icon,
                         bg=self._BG).pack(side='left', padx=(0, 12))
            except Exception:
                self._splash_icon = None

        swatch = tk.Frame(row, bg=self._RED, width=6, height=30)
        swatch.pack(side='left', padx=(0, 10))
        swatch.pack_propagate(False)
        col = tk.Frame(row, bg=self._BG)
        col.pack(side='left')
        tk.Label(col, text='OpenFOAM Mesh Utilities',
                 font=('Segoe UI', 14, 'bold'),
                 fg=self._FG, bg=self._BG).pack(anchor='w')
        tk.Label(col, text='Keysight Technologies',
                 font=('Segoe UI', 9),
                 fg=self._FG_DIM, bg=self._BG).pack(anchor='w')

        tk.Frame(body, bg='#303030', height=1).pack(fill='x', pady=(14, 12))

        self._status = tk.StringVar(value='Starting up…')
        tk.Label(body, textvariable=self._status,
                 font=('Segoe UI', 9), fg='#CCCCCC', bg=self._BG,
                 anchor='w').pack(fill='x')

        tk.Frame(body, bg=self._BG, height=8).pack()

        self._track_frame = tk.Frame(body, bg=self._TRACK, height=6)
        self._track_frame.pack(fill='x')
        self._track_frame.pack_propagate(False)
        self._bar = tk.Frame(self._track_frame, bg=self._RED, height=6)
        self._bar.place(x=0, y=0, relheight=1, width=0)

        tk.Label(body, text='v1.0.0', font=('Segoe UI', 8),
                 fg='#444444', bg=self._BG).pack(anchor='e', pady=(10, 0))

    def set_status(self, text):
        self._status.set(text)
        self.root.update()

    def set_progress(self, frac):
        self._track_frame.update_idletasks()
        w = int(self._track_frame.winfo_width() * max(0.0, min(1.0, frac)))
        self._bar.place_configure(width=w)
        self.root.update()

    def close(self):
        try:
            self.root.destroy()
        except Exception:
            pass


def _run_checks(splash):
    """Run all pre-flight checks. Returns (ok, error_title, error_message)."""
    n = 6
    step = [0]

    def tick(label):
        step[0] += 1
        splash.set_status(label)
        splash.set_progress(step[0] / n)

    # ── 1. WSL reachable ─────────────────────────────────────────────────────
    tick('Checking WSL2…')
    rc, out, err = _wsl('echo ok', timeout=10)
    if rc == -1:
        return False, 'WSL Not Found', (
            'wsl.exe was not found on this machine.\n\n'
            'Fix: enable WSL2 from PowerShell (run as Administrator):\n'
            '  wsl --install\n\n'
            'Restart Windows, then run this launcher again.\n\n'
            'Contact your IT administrator if WSL is blocked by policy.'
        )
    if rc == -2:
        return False, 'WSL Timed Out', (
            'WSL did not respond within 10 seconds.\n\n'
            'WSL may be starting up or unresponsive.\n\n'
            'Fix: open PowerShell and run:\n'
            '  wsl --shutdown\n'
            'Wait 10 seconds, then run this launcher again.'
        )
    if rc != 0 or out != 'ok':
        return False, 'WSL Unreachable', (
            f'WSL2 did not respond correctly (exit code {rc}).\n\n'
            f'Details: {err or "(none)"}\n\n'
            'Try running this in PowerShell:\n'
            '  wsl --status\n\n'
            'Restart WSL with:\n'
            '  wsl --shutdown\n\n'
            'Contact your IT administrator if the problem persists.'
        )

    # ── 2. WSLg display ───────────────────────────────────────────────────────
    tick('Checking WSLg display…')
    rc, out, _ = _wsl('printf "%s%s" "$DISPLAY" "$WAYLAND_DISPLAY"', timeout=10)
    if rc != 0 or not out.strip():
        return False, 'No Display Available', (
            'Neither $DISPLAY nor $WAYLAND_DISPLAY is set inside WSL.\n\n'
            'The GUI requires WSLg (Windows Subsystem for Linux GUI).\n\n'
            'Requirements:\n'
            '  • Windows 11, or Windows 10 Build 21362 or later\n'
            '  • WSL2 (not WSL1)\n\n'
            'Fix: update WSL, then restart it:\n'
            '  wsl --update\n'
            '  wsl --shutdown\n\n'
            'Contact your IT administrator if the problem persists.'
        )

    # ── 3. OpenFOAM bashrc ────────────────────────────────────────────────────
    tick('Checking OpenFOAM installation…')
    rc_2506, _, _ = _wsl(f'test -f {_FOAM_BASHRC_2506}', timeout=10)
    if rc_2506 != 0:
        rc_2312, _, _ = _wsl(f'test -f {_FOAM_BASHRC_2312}', timeout=10)
        if rc_2312 == 0:
            return False, 'Wrong OpenFOAM Version Installed', (
                'OpenFOAM v2312 was found, but this tool requires v2506.\n\n'
                f'Found:    {_FOAM_BASHRC_2312}\n'
                f'Required: {_FOAM_BASHRC_2506}\n\n'
                'Fix: install OpenFOAM 2506 inside WSL.\n'
                'Installation guide (Debian/Ubuntu packages):\n'
                '  https://develop.openfoam.com/Development/openfoam\n'
                '  → Precompiled packages → Debian/Ubuntu\n\n'
                'Contact your system administrator if you cannot install software.'
            )
        return False, 'OpenFOAM Not Found', (
            f'OpenFOAM v2506 was not found at:\n'
            f'  {_FOAM_BASHRC_2506}\n\n'
            'Fix: install OpenFOAM 2506 inside your WSL Ubuntu environment.\n'
            'Installation guide (Debian/Ubuntu packages):\n'
            '  https://develop.openfoam.com/Development/openfoam\n'
            '  → Precompiled packages → Debian/Ubuntu\n\n'
            'Contact your system administrator if you cannot install software.'
        )

    # ── 4. python3 in WSL ────────────────────────────────────────────────────
    tick('Checking Python 3…')
    rc, _, _ = _wsl('python3 --version', timeout=10)
    if rc != 0:
        return False, 'Python 3 Not Found in WSL', (
            'python3 is not available inside WSL.\n\n'
            'Fix: open a WSL terminal and run:\n'
            '  sudo apt-get update\n'
            '  sudo apt-get install -y python3 python3-pip\n\n'
            'Then run this launcher again.'
        )

    # ── 5. Required Python packages ───────────────────────────────────────────
    tick('Checking Python packages…')
    missing = []
    for pkg in _REQUIRED_PACKAGES:
        rc, _, _ = _wsl(f'python3 -c "import {pkg}"', timeout=15)
        if rc != 0:
            missing.append(pkg)

    if missing:
        pkg_str = ' '.join(missing)
        bullets = '\n'.join(f'  • {p}' for p in missing)
        want_install = messagebox.askyesno(
            'Missing Python Packages',
            f'The following packages are missing in WSL:\n\n'
            f'{bullets}\n\n'
            f'Install them now?\n'
            f'(runs: pip3 install {pkg_str} --break-system-packages)',
            icon='warning',
        )
        if want_install:
            splash.set_status(f'Installing {", ".join(missing)}…')
            rc, _, err = _wsl(
                f'pip3 install {pkg_str} --break-system-packages',
                timeout=120,
            )
            if rc != 0:
                return False, 'Package Installation Failed', (
                    f'pip3 install failed for:\n\n'
                    f'{bullets}\n\n'
                    f'Error output:\n{err[:400] if err else "(none)"}\n\n'
                    'Fix: open a WSL terminal and run:\n'
                    f'  pip3 install {pkg_str} --break-system-packages\n\n'
                    'Then run this launcher again.'
                )
        else:
            return False, 'Missing Python Packages', (
                f'These packages must be installed before the GUI can start:\n\n'
                f'{bullets}\n\n'
                f'Open a WSL terminal and run:\n'
                f'  pip3 install {pkg_str} --break-system-packages\n\n'
                'Then run this launcher again.'
            )

    # ── 6. openfoam_ui.py present ─────────────────────────────────────────────
    tick('Checking application files…')
    ui_py = os.path.join(_get_exe_dir(), 'openfoam_ui.py')
    if not os.path.isfile(ui_py):
        return False, 'Application File Missing', (
            f'openfoam_ui.py was not found next to the launcher:\n'
            f'  {ui_py}\n\n'
            'Make sure OpenFOAM_UI.exe and all .py files remain\n'
            'in the same folder. Do not move the .exe out of\n'
            'the 01_utilities folder.'
        )

    return True, None, None


def main():
    splash = _Splash()

    ok, title, msg = _run_checks(splash)

    if not ok:
        messagebox.showerror(title, msg)
        splash.close()
        sys.exit(1)

    splash.set_status('Launching application…')
    splash.set_progress(1.0)
    time.sleep(0.4)

    exe_dir = _get_exe_dir()
    wsl_dir = windows_path_to_wsl(exe_dir)
    launch_cmd = (
        f"source '{_FOAM_BASHRC_2506}' && "
        f"cd '{wsl_dir}' && "
        f"python3 '{wsl_dir}/openfoam_ui.py'"
    )

    try:
        proc = subprocess.Popen(
            [_WSL_EXE, 'bash', '-c', launch_cmd],
            creationflags=_CREATE_NO_WINDOW,
        )
    except Exception as exc:
        messagebox.showerror('Launch Failed', (
            f'Could not start the GUI process:\n\n{exc}\n\n'
            'Try launching manually from a WSL terminal:\n'
            f'  source {_FOAM_BASHRC_2506}\n'
            f'  python3 {wsl_dir}/openfoam_ui.py'
        ))
        splash.close()
        sys.exit(1)

    splash.close()


if __name__ == '__main__':
    main()
