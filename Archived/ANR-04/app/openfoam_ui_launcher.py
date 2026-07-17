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
# Set in _do_checks() once detection succeeds; read by main() to build the
# launch command.  None until detection runs.
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
        """Pump pending tk events without changing state — keeps splash responsive
        during long polling loops where the main thread is otherwise blocked."""
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
    """Return path to an OpenFOAM bashrc — prefer 2506, fall back to 2312.

    Returns None if neither is installed (or WSL is unreachable).
    """
    rc, out, _ = _wsl(
        f'if [ -f {_FOAM_BASHRC_2506} ]; then echo 2506; '
        f'elif [ -f {_FOAM_BASHRC_2312} ]; then echo 2312; '
        f'else echo none; fi',
        timeout=15,
    )
    if rc != 0:
        return None
    v = out.strip()
    if v == '2506':
        return _FOAM_BASHRC_2506
    if v == '2312':
        return _FOAM_BASHRC_2312
    return None


def _build_setup_script(install_openfoam, install_packages):
    """Build the bash setup script body as a single string.

    The script:
      • Installs OpenFOAM 2506 via the official ESI apt repo (uses sudo, so it
        will prompt for the user's password in the terminal).
      • Installs PyQt5 and numpy via pip3 (no sudo needed thanks to
        --break-system-packages).
      • Always touches a sentinel file before the closing read prompt so the
        launcher can detect completion even if the user closes the window
        instead of pressing Enter.

    `set -e` is intentionally NOT used at the top level — if a step fails we
    still want to reach the sentinel + read prompt so the user sees the error
    and the launcher detects the script has finished.
    """
    lines = [
        '#!/usr/bin/env bash',
        'clear || true',
        'echo "==============================================="',
        'echo "  OpenFOAM Mesh Utilities — First-time Setup"',
        'echo "==============================================="',
        'echo',
        'overall=0',
    ]
    if install_openfoam:
        lines.extend([
            'echo "Step: Installing OpenFOAM 2506"',
            'echo "Sudo will prompt for your password — that is expected."',
            'echo',
            'curl -fsSL https://dl.openfoam.com/add-apt-repository.sh | sudo bash',
            'rc_repo=$?',
            'sudo apt-get update',
            'rc_update=$?',
            'sudo apt-get install -y openfoam2506',
            'rc_install=$?',
            'if [ $rc_repo -ne 0 ] || [ $rc_update -ne 0 ] || [ $rc_install -ne 0 ]; then',
            '  echo',
            '  echo "[ERROR] OpenFOAM installation failed."',
            '  overall=1',
            'fi',
            'echo',
        ])
    if install_packages:
        lines.extend([
            'echo "Step: Installing Python packages (PyQt5, numpy)"',
            'pip3 install PyQt5 numpy --break-system-packages',
            'if [ $? -ne 0 ]; then',
            '  echo "[ERROR] Python package installation failed."',
            '  overall=1',
            'fi',
            'echo',
        ])
    lines.extend([
        'echo "==============================================="',
        'if [ "$overall" = "0" ]; then',
        '  echo "  Setup complete!"',
        'else',
        '  echo "  Setup FAILED — review messages above."',
        'fi',
        'echo "==============================================="',
        'touch "$HOME/.openfoam_ui_setup_done"',
        'echo',
        'read -p "Press Enter to close this window... " _',
    ])
    return '\n'.join(lines) + '\n'


def _write_setup_script(install_openfoam, install_packages):
    """Write the setup script into the WSL home directory.

    Uses base64 over the wsl pipe to avoid any Windows-side quoting or newline
    pitfalls — Python encodes the script body, bash decodes it inside WSL and
    writes the file.  Counts as "writing via WSL echo/cat", not Python I/O,
    because no Python open()/write() touches the WSL filesystem.

    Returns (ok, error_message).
    """
    body = _build_setup_script(install_openfoam, install_packages)
    body_b64 = base64.b64encode(body.encode('utf-8')).decode('ascii')
    cmd = (
        f'echo "{body_b64}" | base64 -d > "{_SETUP_SCRIPT_WSL}" && '
        f'chmod +x "{_SETUP_SCRIPT_WSL}"'
    )
    rc, _, err = _wsl(cmd, timeout=20)
    if rc != 0:
        return False, err or f'wsl write returned exit code {rc}'
    return True, None


def _launch_install_terminal(splash):
    """Launch the setup script in a visible terminal and wait for it to finish.

    Strategy:
      1. Clear any stale sentinel file.
      2. Try Windows Terminal (wt.exe) first, fall back to cmd.exe.
      3. Poll the sentinel file inside WSL — appears when the script reaches
         its final read prompt.  Also polls for the bash script PID via pgrep
         to detect early termination (user closing the terminal window before
         install completes).

    The script process is the authoritative signal because:
      • wt.exe forks the terminal off and exits immediately — proc.wait() would
        return long before the user finishes installing.
      • cmd.exe /c start without /wait also exits immediately.

    Returns True if the sentinel was written (script ran to completion),
    False on launch failure / timeout / early termination.
    """
    # Clear any sentinel from a previous attempt so we don't mistake it for
    # a successful run of this attempt.
    _wsl(f'rm -f "{_SETUP_SENTINEL_WSL}"', timeout=5)

    inner = f'bash "{_SETUP_SCRIPT_WSL}"'
    launchers = [
        # Windows Terminal — opens its own window in the Ubuntu profile.
        ['wt.exe', '-p', 'Ubuntu', '--',
         _WSL_EXE, 'bash', '-c', inner],
        # Fallback — works on any Windows install.
        ['cmd.exe', '/c', 'start', '',
         _WSL_EXE, 'bash', '-c', inner],
    ]
    proc = None
    for cmd in launchers:
        try:
            proc = subprocess.Popen(cmd)
            break
        except (FileNotFoundError, OSError):
            continue
        except Exception:
            continue
    if proc is None:
        return False

    # proc.wait() per the spec — for wt.exe this returns immediately, for
    # cmd.exe /c start it also returns immediately.  The real completion
    # signal is the sentinel file polled below.
    try:
        proc.wait()
    except Exception:
        pass

    splash.set_status(
        'Setup running — follow the prompts in the terminal window…'
    )

    deadline = time.time() + 30 * 60  # 30 min absolute cap
    start_time = time.time()
    startup_grace = 20  # don't flag "process gone" during this window
    script_dead_since = None

    while time.time() < deadline:
        splash.pump()

        # Primary completion signal — sentinel file.
        rc, out, _ = _wsl(
            f'test -f "{_SETUP_SENTINEL_WSL}" && echo done',
            timeout=5,
        )
        if out.strip() == 'done':
            return True

        # Secondary signal — if the bash process disappears without writing
        # the sentinel, the user closed the terminal early.  Only enforced
        # after a startup grace period so we don't false-positive on the
        # initial slow WSL boot.
        if time.time() - start_time > startup_grace:
            rc, out, _ = _wsl('pgrep -f openfoam_ui_setup.sh', timeout=5)
            script_alive = (rc == 0 and out.strip())
            if not script_alive:
                if script_dead_since is None:
                    script_dead_since = time.time()
                elif time.time() - script_dead_since > 10:
                    return False
            else:
                script_dead_since = None

        time.sleep(3)

    return False


# ─────────────────────────────────────────────────────────────────────────────
# Pre-flight checks
# ─────────────────────────────────────────────────────────────────────────────

def _do_checks(splash):
    """Run a single pass of pre-flight checks.

    Returns one of:
      True                     — all good, ready to launch.
      (False, title, message)  — hard failure, caller shows the dialog & exits.
      ('install', None, None)  — interactive install was attempted, caller
                                 should re-run checks from the top.
    """
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

    # ── 3. OpenFOAM bashrc — independent check, surfaces missing case clearly ─
    tick('Checking OpenFOAM installation…')
    bashrc = _detect_openfoam_bashrc()
    needs_openfoam = bashrc is None

    # ── 4. python3 ────────────────────────────────────────────────────────────
    tick('Checking Python 3…')
    rc, _, _ = _wsl('python3 --version', timeout=10)
    if rc != 0:
        # python3 install requires sudo apt-get and is unusual on modern Ubuntu
        # (which ships python3 by default).  Treat as a hard error rather than
        # bundling it into the interactive installer.
        return False, 'Python 3 Not Found in WSL', (
            'python3 is not available inside WSL.\n\n'
            'Fix: open a WSL terminal and run:\n'
            '  sudo apt-get update\n'
            '  sudo apt-get install -y python3 python3-pip\n\n'
            'Then run this launcher again.'
        )

    # ── 5. Python packages ────────────────────────────────────────────────────
    tick('Checking Python packages…')
    pkgs = ' '.join(_REQUIRED_PACKAGES)
    rc, out, _ = _wsl(
        f'miss=""; '
        f'for p in {pkgs}; do python3 -c "import $p" 2>/dev/null || miss="$miss $p"; done; '
        f'printf "%s" "$miss"',
        timeout=20,
    )
    missing = out.strip().split() if rc == 0 else list(_REQUIRED_PACKAGES)
    needs_packages = bool(missing)

    # ── Interactive install if OpenFOAM or packages are missing ──────────────
    if needs_openfoam or needs_packages:
        bullets = []
        if needs_openfoam:
            bullets.append('  • OpenFOAM 2506 (requires your sudo password)')
        if needs_packages:
            bullets.append(f'  • Python packages: {", ".join(missing)}')
        items = '\n'.join(bullets)

        ok = messagebox.askyesno(
            'Setup Required',
            (
                f'The following components are missing and must be installed '
                f'before the GUI can start:\n\n'
                f'{items}\n\n'
                'Click Yes to open a setup terminal window. Sudo will prompt '
                'for your password inside that window — that is normal and '
                'expected.\n\n'
                'Click No to exit and install manually.'
            ),
            icon='info',
        )
        if not ok:
            return False, 'Setup Required', (
                'These components must be installed before the GUI can start:\n\n'
                f'{items}\n\n'
                'See the project README for manual installation instructions, '
                'then run this launcher again.'
            )

        splash.set_status('Preparing setup script…')
        ok_write, err = _write_setup_script(needs_openfoam, needs_packages)
        if not ok_write:
            return False, 'Could Not Write Setup Script', (
                'Failed to write the setup script to ~/openfoam_ui_setup.sh '
                'inside WSL:\n\n'
                f'{err or "(no error message)"}\n\n'
                'Try installing the missing components manually inside WSL.'
            )

        ok_term = _launch_install_terminal(splash)
        if not ok_term:
            return False, 'Setup Did Not Complete', (
                'The setup terminal could not be launched, or the terminal was '
                'closed before installation completed.\n\n'
                'Open a WSL terminal manually and run:\n'
                '  bash ~/openfoam_ui_setup.sh\n\n'
                'Then run this launcher again.'
            )
        return ('install', None, None)

    # ── All present — record the bashrc that the launch command will source ─
    global _DETECTED_BASHRC
    _DETECTED_BASHRC = bashrc

    # ── 6. openfoam_ui.py present — local file check ─────────────────────────
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

    return True


def _run_checks(splash):
    """Run pre-flight checks, retrying once after an interactive install."""
    for attempt in range(2):
        if attempt > 0:
            splash.set_status('Re-running pre-flight checks…')
            splash.set_progress(0.0)
        result = _do_checks(splash)
        if result is True:
            return True, None, None
        if isinstance(result, tuple) and result[0] == 'install':
            continue
        return result
    # Second pass still wanted an install — installer didn't fix everything.
    return False, 'Setup Not Complete', (
        'The first installation attempt finished but required components are '
        'still missing.\n\n'
        'Open a WSL terminal manually and run:\n'
        '  bash ~/openfoam_ui_setup.sh\n\n'
        'Read any error messages, address them, then run this launcher again.'
    )


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
