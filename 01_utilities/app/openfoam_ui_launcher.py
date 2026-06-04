"""
openfoam_ui_launcher.py — Windows launcher for OpenFOAM Mesh Utilities GUI.

Runs pre-flight checks via WSL, then launches openfoam_ui.py inside WSL.
Stdlib only: tkinter, subprocess, sys, os, time, base64.
"""
import tkinter as tk
from tkinter import messagebox
import subprocess
import sys
import os
import time
import base64

_CREATE_NO_WINDOW = 0x08000000
_WSL_EXE = 'wsl'
_FOAM_BASHRC_2506 = '/usr/lib/openfoam/openfoam2506/etc/bashrc'
_FOAM_BASHRC_2312 = '/usr/lib/openfoam/openfoam2312/etc/bashrc'
_REQUIRED_PACKAGES = ['PyQt5', 'numpy']

# Path to the OpenFOAM bashrc that pre-flight confirmed exists.
# Set by _detect_openfoam_bashrc() once detection succeeds; read by main() to
# build the launch command.  None until detection runs.
_DETECTED_BASHRC = None

# Path of the install sentinel inside WSL — written by the setup script as its
# last action before the "Press Enter to close" prompt.  Used by the polling
# loop to detect completion regardless of which terminal launcher was used.
_SETUP_SENTINEL_WSL = '$HOME/.openfoam_ui_setup_done'
_SETUP_SCRIPT_WSL = '$HOME/openfoam_ui_setup.sh'


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
        """Build the splash layout: red accent bar, logo/title row, status label, progress bar."""
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

    def pump(self):
        """Pump pending tk events without changing state — keeps splash
        responsive during long polling loops where the main thread would
        otherwise be blocked in sleep()/subprocess.run()."""
        try:
            self.root.update()
        except Exception:
            pass

    def close(self):
        try:
            self.root.destroy()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Interactive install flow
# ─────────────────────────────────────────────────────────────────────────────

def _detect_openfoam_bashrc():
    """Detect which OpenFOAM bashrc is available — prefer 2506, fall back to
    2312.  Updates the module-level _DETECTED_BASHRC and returns it (or None
    if neither version is installed)."""
    global _DETECTED_BASHRC
    rc, out, _ = _wsl(
        f'test -f {_FOAM_BASHRC_2506} && echo 2506 || '
        f'(test -f {_FOAM_BASHRC_2312} && echo 2312 || echo none)',
        timeout=10,
    )
    if rc == 0 and out.strip() == '2506':
        _DETECTED_BASHRC = _FOAM_BASHRC_2506
    elif rc == 0 and out.strip() == '2312':
        _DETECTED_BASHRC = _FOAM_BASHRC_2312
    else:
        _DETECTED_BASHRC = None
    return _DETECTED_BASHRC


def _build_setup_script(install_openfoam, install_packages):
    """Build the bash setup script body as a single string.

    Always installs the Qt/XCB system libraries (every fresh Ubuntu WSL
    install needs them for PyQt5 to display).  Optionally installs OpenFOAM
    2506 and Python packages.  Always touches the sentinel and prompts for
    Enter at the end.

    `set -e` is intentionally NOT used — every section must run to
    completion so the sentinel is always touched and the user sees every
    error in the terminal.
    """
    lines = [
        '#!/usr/bin/env bash',
        'echo "============================================"',
        'echo " OpenFOAM GUI — First-Time Setup"',
        'echo "============================================"',
        'echo ""',
        '',
        'echo "=== Installing Qt/XCB system libraries ==="',
        'sudo apt-get install -y \\',
        '  libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \\',
        '  libxcb-randr0 libxcb-render-util0 libxcb-xinerama0 \\',
        '  libxcb-xfixes0 libxcb-cursor0 libxkbcommon-x11-0',
        'echo ""',
        '',
    ]
    if install_openfoam:
        lines.extend([
            'echo "=== Installing OpenFOAM 2506 ==="',
            'curl -s https://dl.openfoam.com/add-apt-repository.sh | sudo bash',
            'sudo apt-get update',
            'sudo apt-get install -y openfoam2506',
            'echo ""',
            '',
        ])
    if install_packages:
        pkgs = ' '.join(install_packages)
        lines.extend([
            'echo "=== Installing Python packages ==="',
            f'pip3 install {pkgs} --break-system-packages',
            'echo ""',
            '',
        ])
    lines.extend([
        'echo "============================================"',
        'echo " Setup finished."',
        'echo "============================================"',
        'touch $HOME/.openfoam_ui_setup_done',
        'read -p "Press Enter to close this window..."',
    ])
    return '\n'.join(lines) + '\n'


def _write_setup_script(install_openfoam, install_packages):
    """Write the setup script into the WSL home directory via base64.

    Returns True if the WSL command succeeded, False otherwise.
    """
    body = _build_setup_script(install_openfoam, install_packages)
    b64 = base64.b64encode(body.encode()).decode()
    rc, _, _ = _wsl(
        f'echo "{b64}" | base64 -d > {_SETUP_SCRIPT_WSL} && '
        f'chmod +x {_SETUP_SCRIPT_WSL}',
        timeout=15,
    )
    return rc == 0


def _launch_install_terminal(splash):
    """Launch the setup script in a visible terminal and wait for it to finish.

    Strategy:
      1. Clear stale sentinel.
      2. Try Windows Terminal (wt.exe) first, fall back to cmd.exe.
         Both are launched with CREATE_NO_WINDOW so the launcher itself
         doesn't spawn a console; the terminal app shows its own window.
      3. Poll the sentinel file (written as the script's last action) every
         2 seconds, up to 30 minutes.  After a 20 s startup grace period,
         also watch for the bash script disappearing without writing the
         sentinel (user closed the terminal early); require 3 consecutive
         "gone" readings to avoid false positives during apt's brief lulls.

    proc.wait() is deliberately NOT called: wt.exe and `cmd /c start` both
    fork off the terminal and exit immediately, so the only authoritative
    completion signal is the sentinel.
    """
    # Clear any sentinel from a previous attempt so we don't mistake it for
    # success on this attempt.
    _wsl(f'rm -f {_SETUP_SENTINEL_WSL}', timeout=5)

    proc = None
    try:
        proc = subprocess.Popen(
            ['wt.exe', '-p', 'Ubuntu', '--',
             'wsl', 'bash', _SETUP_SCRIPT_WSL],
            creationflags=_CREATE_NO_WINDOW,
        )
    except (FileNotFoundError, OSError):
        try:
            proc = subprocess.Popen(
                ['cmd.exe', '/c', 'start', '',
                 'wsl', 'bash', '-c', f'bash {_SETUP_SCRIPT_WSL}'],
                creationflags=_CREATE_NO_WINDOW,
            )
        except (FileNotFoundError, OSError):
            return False

    if proc is None:
        return False

    splash.set_status(
        'Setup running — follow the prompts in the terminal window…'
    )

    max_iterations = 1800        # 30 min ÷ 2 s
    grace_iterations = 10        # 20 s before we start watching pgrep
    gone_streak = 0

    for i in range(max_iterations):
        splash.pump()
        time.sleep(2)

        # Primary completion signal — sentinel file.
        rc, out, _ = _wsl(
            f'test -f {_SETUP_SENTINEL_WSL} && echo yes',
            timeout=5,
        )
        if out.strip() == 'yes':
            return True

        # Secondary signal — script process disappeared without writing the
        # sentinel.  Only enforced after the startup grace window so we don't
        # false-positive while WSL is still booting.
        if i >= grace_iterations:
            rc, out, _ = _wsl(
                'pgrep -f openfoam_ui_setup.sh > /dev/null && '
                'echo running || echo gone',
                timeout=5,
            )
            if out.strip() == 'gone':
                gone_streak += 1
                if gone_streak >= 3:
                    return False
            else:
                gone_streak = 0

    return False


# ─────────────────────────────────────────────────────────────────────────────
# Pre-flight checks
# ─────────────────────────────────────────────────────────────────────────────

def _do_checks(splash):
    """Run a single pass of pre-flight checks.

    Returns one of:
      (True, None, None)        — all good, ready to launch.
      (False, title, message)   — hard failure, caller shows the dialog & exits.
      'install'                 — interactive install was attempted; caller
                                  should re-run checks from the top.
    """
    n = 7
    step = [0]

    def tick(label):
        step[0] += 1
        splash.set_status(label)
        splash.set_progress(step[0] / n)

    # ── Step 1: WSL reachable ────────────────────────────────────────────────
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

    # ── Step 2: WSLg display ─────────────────────────────────────────────────
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

    # ── Step 3: OpenFOAM bashrc — detect, don't fail here ────────────────────
    tick('Checking OpenFOAM installation…')
    bashrc = _detect_openfoam_bashrc()
    install_openfoam = bashrc is None

    # ── Step 4: python3 present ──────────────────────────────────────────────
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

    # ── Step 5: Python packages — detect, don't install yet ──────────────────
    tick('Checking Python packages…')
    pkgs = ' '.join(_REQUIRED_PACKAGES)
    rc, out, _ = _wsl(
        f'miss=""; '
        f'for p in {pkgs}; do python3 -c "import $p" 2>/dev/null || miss="$miss $p"; done; '
        f'printf "%s" "$miss"',
        timeout=20,
    )
    missing = out.strip().split() if rc == 0 else list(_REQUIRED_PACKAGES)

    # ── Step 6: Interactive install gate ─────────────────────────────────────
    tick('Reviewing installation requirements…')
    if install_openfoam or missing:
        bullets = []
        if install_openfoam:
            bullets.append('  • OpenFOAM 2506 (required for mesh generation)')
        bullets.append('  • Qt/XCB system libraries (required by the GUI)')
        for p in missing:
            bullets.append(f'  • {p}')
        items = '\n'.join(bullets)

        ok = messagebox.askyesno(
            'First-Time Setup Required',
            (
                'The following components need to be installed in WSL:\n\n'
                f'{items}\n\n'
                'A terminal window will open so you can enter your\n'
                'sudo password when prompted.\n\n'
                'Install now?'
            ),
            icon='info',
        )
        if not ok:
            return False, 'Setup Required', (
                'These components must be installed before the GUI can start:\n\n'
                f'{items}\n\n'
                'Run the launcher again when you are ready to install.'
            )

        if not _write_setup_script(install_openfoam, missing):
            return False, 'Setup Script Failed', (
                'Failed to write the setup script to ~/openfoam_ui_setup.sh '
                'inside WSL.\n\n'
                'Try installing the missing components manually inside WSL.'
            )

        splash.set_status('Waiting for setup to complete…')
        if _launch_install_terminal(splash):
            return 'install'
        return False, 'Setup Cancelled or Failed', (
            'The setup terminal was closed before setup completed.\n\n'
            'Please run the launcher again and complete the setup\n'
            'when prompted.'
        )

    # ── Step 7: openfoam_ui.py present ───────────────────────────────────────
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


def _run_checks(splash):
    """Run pre-flight checks; allow one interactive-install retry."""
    result = _do_checks(splash)
    if result == 'install':
        splash.set_status('Re-running pre-flight checks…')
        splash.set_progress(0.0)
        result = _do_checks(splash)
    if result == 'install':
        return False, 'Setup Not Complete', (
            'Installation did not complete successfully.\n\n'
            'Please run the launcher again after setup is finished.\n\n'
            'If problems persist, open a WSL terminal and run:\n'
            '  sudo apt-get install -y openfoam2506\n'
            '  pip3 install PyQt5 numpy --break-system-packages'
        )
    return result


def main():
    """Show the splash, run pre-flight checks, then launch openfoam_ui.py inside WSL."""
    splash = _Splash()

    ok, title, msg = _run_checks(splash)

    if not ok:
        messagebox.showerror(title, msg)
        splash.close()
        sys.exit(1)

    splash.set_status('Launching application…')
    splash.set_progress(1.0)
    time.sleep(0.4)

    # Prefer the bashrc that pre-flight detected; fall back defensively.
    bashrc = _DETECTED_BASHRC or _FOAM_BASHRC_2506
    exe_dir = _get_exe_dir()
    wsl_dir = windows_path_to_wsl(exe_dir)
    launch_cmd = (
        f"source '{bashrc}' && "
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
            f'  source {bashrc}\n'
            f'  python3 {wsl_dir}/openfoam_ui.py'
        ))
        splash.close()
        sys.exit(1)

    splash.close()


if __name__ == '__main__':
    main()

