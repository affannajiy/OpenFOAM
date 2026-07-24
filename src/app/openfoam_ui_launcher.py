"""
openfoam_ui_launcher.py — Windows launcher for OpenFOAM Mesh Utilities GUI.

Runs pre-flight checks via WSL, then launches openfoam_ui.py inside WSL.
Stdlib only: tkinter, subprocess, sys, os, time, base64, tempfile, winreg.

Startup philosophy
------------------
The launcher never asks the user to restart Windows.  A cold WSL VM is
given up to 90 seconds to boot (with a live countdown on the splash), and
every recoverable failure ends in a dialog with a [Try Again] button — and,
where WSL state could be the culprit, a [Restart WSL] button that runs
`wsl --shutdown` on the user's behalf (after a warning, since it stops all
running WSL programs).

First-time setup is apt-only: Qt/XCB display libraries plus python3-pyqt5 /
python3-numpy / python3-jinja2 in a single apt transaction (no pip — fresh Ubuntu WSL images
ship without pip3, which used to make the old pip-based setup fail and loop).
The setup script records a per-component status line into the sentinel file
(`aptupdate=ok`, `packages=fail:100`, …) so the launcher can report exactly
what failed and how to fix it manually.

Self-healing installs: missing WSL → elevated `wsl --install --no-distribution`
(with an optional one-time Windows restart offer); no distro → `wsl --install
-d Ubuntu --no-launch` plus a guided first-run terminal for the UNIX account;
WSL1 distro → offered in-place `wsl --set-version 2` conversion; missing WSLg
display env → offered `wsl --update`.  Before first-time setup the launcher
probes the download servers (bash /dev/tcp — no curl dependency) and free disk
space so failures surface with the real reason instead of mid-apt.  Every
error dialog has a "Copy Details" button (versions + log tail → clipboard).

All WSL interaction targets one explicitly chosen distro (-d <name>): the
registry default unless that is a utility distro (docker-desktop, rancher,
podman), in which case the first Ubuntu* distro is used instead.

Diagnostics are appended to %TEMP%/openfoam_ui_launcher.log; every error
dialog references that path.
"""
import tkinter as tk
import subprocess
import sys
import os
import time
import base64
import tempfile
import json
import glob
import webbrowser

try:
    import winreg
except ImportError:          # non-Windows (dev only)
    winreg = None

_CREATE_NO_WINDOW = 0x08000000
_WSL_EXE = 'wsl'
_FOAM_BASHRC_2506 = '/usr/lib/openfoam/openfoam2506/etc/bashrc'
_FOAM_BASHRC_2312 = '/usr/lib/openfoam/openfoam2312/etc/bashrc'

# (import name, apt package) pairs — checked by import, installed via apt.
_REQUIRED_PACKAGES = [('PyQt5', 'python3-pyqt5'), ('numpy', 'python3-numpy'),
                      ('jinja2', 'python3-jinja2')]

# Distros that exist for tooling (Docker Desktop etc.) — never run the GUI there.
_UTILITY_DISTROS = {
    'docker-desktop', 'docker-desktop-data',
    'rancher-desktop', 'rancher-desktop-data',
}

_WSL_BOOT_BUDGET_S = 90       # max wait for a cold WSL VM to boot
_DISPLAY_BUDGET_S = 30        # max wait for the WSLg compositor
_MIN_WSLG_BUILD = 21362       # first Windows build with WSLg support
_WSL_INSTALL_BUDGET_S = 1200  # max wait for `wsl --install` / distro download
_FIRSTRUN_BUDGET_S = 900      # max wait for Ubuntu first-run user creation
_CONVERT_BUDGET_S = 1800      # max wait for WSL1 → WSL2 conversion

# Free-space requirements (GiB) checked before first-time setup.
_DISK_NEED_OPENFOAM_GB = 6
_DISK_NEED_BASE_GB = 1

# Path to the OpenFOAM bashrc that pre-flight confirmed exists.
# Set by the merged probe in _do_checks (or restored from the fast-path
# sentinel); read by main() to build the launch command.
_DETECTED_BASHRC = None

# WSL distro all commands target.  Set by _detect_distro(); None means
# "let wsl.exe pick the default" (only before detection has run).
_DISTRO = None

# Path of the install sentinel inside WSL — written (via mv, so it appears
# atomically and only when complete) as the setup script's last action before
# the "Press Enter to close" prompt.  Contains one `component=ok|fail:<rc>`
# line per setup section.
_SETUP_SENTINEL_WSL = '$HOME/.openfoam_ui_setup_done'
_SETUP_STATUS_TMP_WSL = '$HOME/.openfoam_ui_setup_status.tmp'
_SETUP_SCRIPT_WSL = '$HOME/openfoam_ui_setup.sh'

_LOG_PATH = os.path.join(tempfile.gettempdir(), 'openfoam_ui_launcher.log')

# Fast-path sentinel: written after a fully successful launch (checks passed
# AND the GUI actually came up).  While it exists, later runs skip the full
# check chain — one cheap WSL validation call instead of ~9 spawns + a Qt
# probe.  Deleted whenever validation or the GUI launch fails, which drops
# the next run back to the full self-healing checks automatically.
_FASTPATH_SENTINEL = os.path.join(tempfile.gettempdir(),
                                  'openfoam_ui_checks_ok.json')

# Sentinel written after the optional ParaView dialog is shown once, so a
# missing (but optional) ParaView never nags the user on every launch.
_PARAVIEW_DECLINED_SENTINEL = os.path.join(tempfile.gettempdir(),
                                           'openfoam_ui_paraview_declined')


def _load_fastpath():
    """Return {'distro': …, 'bashrc': …} from the sentinel, or None."""
    try:
        with open(_FASTPATH_SENTINEL, encoding='utf-8') as f:
            data = json.load(f)
        if data.get('distro') and data.get('bashrc'):
            return data
    except Exception:
        pass
    return None


def _save_fastpath():
    try:
        with open(_FASTPATH_SENTINEL, 'w', encoding='utf-8') as f:
            json.dump({'distro': _DISTRO, 'bashrc': _DETECTED_BASHRC}, f)
        _log('fast-path sentinel saved')
    except Exception:
        pass


def _clear_fastpath():
    try:
        os.remove(_FASTPATH_SENTINEL)
        _log('fast-path sentinel cleared')
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Single-instance guard
# ─────────────────────────────────────────────────────────────────────────────

# Keep a module-level reference to the mutex handle so it stays open for the
# launcher's whole lifetime; Windows releases it automatically at process exit.
_INSTANCE_MUTEX = None

_GUI_WINDOW_TITLE = 'OpenFOAM GUI'   # must match MainWindow.setWindowTitle


def _focus_existing_gui():
    """If the GUI is already open (WSLg windows are real Windows windows),
    bring it to the foreground and return True — the standard second-click
    behaviour (Word, VS Code, …): focus, don't duplicate."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, _GUI_WINDOW_TITLE)
        if hwnd:
            user32.ShowWindow(hwnd, 9)          # SW_RESTORE (un-minimise)
            user32.SetForegroundWindow(hwnd)
            return True
    except Exception as exc:
        _log(f'focus-existing check failed: {exc}')
    return False


def _acquire_instance_mutex():
    """Take the launcher's named mutex.  Returns False when another launcher
    is already mid-startup (splash/checks phase, before the GUI window exists
    for _focus_existing_gui to find).  Fails open on any API error — a rare
    double window beats a launcher that refuses to start."""
    global _INSTANCE_MUTEX
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        _INSTANCE_MUTEX = kernel32.CreateMutexW(
            None, False, 'Local\\OpenFOAM_UI_Launcher')
        if kernel32.GetLastError() == 183:      # ERROR_ALREADY_EXISTS
            return False
    except Exception as exc:
        _log(f'instance mutex failed (continuing): {exc}')
    return True

# Per-component failure help: label, manual fix command(s), likely cause.
_FAIL_INFO = {
    'aptupdate': (
        'Package list update (apt-get update)',
        'sudo apt-get update',
        'archive.ubuntu.com may be blocked by a corporate proxy — contact IT.',
    ),
    'packages': (
        'System libraries / Python packages',
        'sudo apt-get install -y python3-pyqt5 python3-numpy python3-jinja2',
        'archive.ubuntu.com may be blocked by a corporate proxy — contact IT.',
    ),
    'openfoam': (
        'OpenFOAM 2506',
        'curl -fsSL https://dl.openfoam.com/add-debian-repo.sh | sudo bash\n'
        '    sudo apt-get update\n'
        '    sudo apt-get install -y openfoam2506',
        'dl.openfoam.com may be blocked by a corporate proxy — contact IT.',
    ),
}


def _log(msg):
    """Append a timestamped line to the Windows-side diagnostic log."""
    try:
        with open(_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S') + '  ' + msg + '\n')
    except Exception:
        pass


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
    """Run a bash command inside the selected WSL distro.

    `--exec` is required: without it wsl.exe re-evaluates the command line
    through the distro's default shell, which expands `$var`/`$?` and strips
    quotes BEFORE our `bash -c` runs.  That double evaluation silently broke
    every $-containing check (e.g. the missing-package loop always reported
    "nothing missing").  With --exec, bash receives `cmd` exactly as written.

    Returns (returncode, stdout, stderr).
    """
    args = [_WSL_EXE]
    if _DISTRO:
        args += ['-d', _DISTRO]
    args += ['--exec', 'bash', '-c', cmd]
    try:
        r = subprocess.run(
            args,
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


def _decode_console(raw):
    """Decode wsl.exe console bytes (UTF-16LE on most builds) to clean text."""
    raw = raw or b''
    if b'\x00' in raw:
        text = raw.decode('utf-16-le', errors='replace')
    else:
        text = raw.decode(errors='replace')
    return text.replace('\x00', '').strip()


def _run_win_streaming(args, splash, status, timeout_s):
    """Run a Windows-side command while keeping the splash alive.

    Polls every second, updating the splash status with an elapsed-seconds
    counter.  Returns (returncode, combined_output_text); rc -2 on timeout,
    -1 if the executable is missing.
    """
    _log(f'win cmd: {" ".join(args)}')
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=_CREATE_NO_WINDOW,
        )
    except (FileNotFoundError, OSError) as exc:
        return -1, str(exc)
    start = time.time()
    while proc.poll() is None:
        if time.time() - start > timeout_s:
            proc.kill()
            _log(f'win cmd timed out after {timeout_s}s')
            return -2, ''
        if splash is not None:
            splash.set_status(f'{status} ({int(time.time() - start)}s)')
            splash.pump()
        time.sleep(1)
    out = _decode_console(proc.stdout.read() if proc.stdout else b'')
    _log(f'win cmd rc={proc.returncode} out={out[:200]!r}')
    return proc.returncode, out


def _run_elevated(exe, arg_list, splash, status, timeout_s=900):
    """Run a Windows command elevated (UAC prompt) and wait for it.

    Uses PowerShell Start-Process -Verb RunAs; the elevated process's own
    output is not capturable, so only the exit code is meaningful.  A UAC
    decline makes Start-Process throw → non-zero rc.
    """
    quoted = ','.join(f"'{a}'" for a in arg_list)
    ps = (f"$p = Start-Process -FilePath '{exe}' -ArgumentList {quoted} "
          f"-Verb RunAs -Wait -PassThru; exit $p.ExitCode")
    return _run_win_streaming(
        ['powershell', '-NoProfile', '-Command', ps],
        splash, status, timeout_s)


def _is_uac_declined(out):
    """True when elevated-command output shows the user declined the UAC
    prompt (PowerShell Start-Process throws 'canceled by the user',
    Win32 error 0x800704C7 / 1223)."""
    lowered = (out or '').lower()
    return ('canceled by the user' in lowered
            or 'cancelled by the user' in lowered
            or '0x800704c7' in lowered
            or 'error 1223' in lowered)


def _windows_build():
    """Return the Windows build number as int, or None if unreadable."""
    if winreg is None:
        return None
    try:
        k = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r'SOFTWARE\Microsoft\Windows NT\CurrentVersion')
        b, _ = winreg.QueryValueEx(k, 'CurrentBuildNumber')
        return int(b)
    except (OSError, ValueError):
        return None


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

        tk.Label(body, text='v1.1.0', font=('Segoe UI', 8),
                 fg='#444444', bg=self._BG).pack(anchor='e', pady=(10, 0))

    def set_status(self, text):
        """Update the status line under the title and repaint immediately."""
        self._status.set(text)
        self.root.update()

    def set_progress(self, frac):
        """Fill the red progress bar to `frac` (0.0–1.0) of its track width."""
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
        """Destroy the splash window (safe to call more than once)."""
        try:
            self.root.destroy()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Dialog helpers — always parented to the splash and kept on top so they can't
# hide behind other windows.
# ─────────────────────────────────────────────────────────────────────────────

def _diagnostics_report(title, msg):
    """Build a plain-text diagnostics report for IT tickets / bug reports."""
    lines = [
        'OpenFOAM Mesh Utilities — launcher diagnostics',
        time.strftime('%Y-%m-%d %H:%M:%S'),
        f'Error: {title}',
        '',
        msg,
        '',
        f'Windows build: {_windows_build()}',
        f'Target distro: {_DISTRO}',
    ]
    try:
        r = subprocess.run([_WSL_EXE, '--version'], capture_output=True,
                           timeout=10, creationflags=_CREATE_NO_WINDOW)
        lines += ['', 'wsl --version:', _decode_console(r.stdout)]
    except Exception as exc:
        lines += ['', f'wsl --version failed: {exc}']
    try:
        with open(_LOG_PATH, encoding='utf-8', errors='replace') as f:
            tail = f.readlines()[-60:]
        lines += ['', f'Log tail ({_LOG_PATH}):'] + [ln.rstrip() for ln in tail]
    except Exception:
        lines += ['', '(log unavailable)']
    return '\n'.join(lines)


def _show_error(splash, title, msg):
    """Modal error dialog; the diagnostic log path is always appended.

    Built on _choice_dialog rather than tkinter's native messagebox because
    the native one places itself wherever Windows decides (often the top-left
    of the screen); _choice_dialog centers over the splash."""
    _log(f'ERROR DIALOG: {title}')
    _choice_dialog(splash, title, msg + f'\n\nLog: {_LOG_PATH}',
                   [('ok', 'OK')], report=True)


def _ask_yes_no(splash, title, msg, icon='info'):
    """Modal Yes/No question; returns True for Yes. Centered like _show_error
    (the `icon` argument is kept for call-site compatibility but unused)."""
    return _choice_dialog(splash, title, msg,
                          [('yes', 'Yes'), ('no', 'No')]) == 'yes'


def _choice_dialog(splash, title, msg, buttons, report=False, copy_cmd=None):
    """Modal dialog with arbitrary buttons.

    buttons: list of (key, label) tuples, shown left to right.
    Returns the key of the clicked button; closing the window with X
    returns the last button's key (the dismiss action).
    report=True adds a "Copy Details" button that copies a full
    diagnostics report (versions + log tail) to the clipboard without
    closing the dialog — for pasting into IT tickets.
    copy_cmd='<command>' adds a "Copy Command" button that copies that
    exact command to the clipboard — for pasting into an admin PowerShell.
    """
    _log(f'CHOICE DIALOG: {title}')
    top = tk.Toplevel(splash.root)
    top.title(title)
    top.transient(splash.root)
    top.resizable(False, False)
    top.attributes('-topmost', True)

    choice = {'v': buttons[-1][0]}

    body = tk.Frame(top, padx=18, pady=14)
    body.pack(fill='both', expand=True)
    tk.Label(body, text=msg, justify='left', anchor='w',
             wraplength=460, font=('Segoe UI', 9)).pack(fill='x')

    btn_row = tk.Frame(body)
    btn_row.pack(fill='x', pady=(14, 0))

    def _pick(key):
        choice['v'] = key
        top.destroy()

    for key, label in buttons:
        tk.Button(btn_row, text=label, width=max(12, len(label) + 2),
                  command=lambda k=key: _pick(k)).pack(side='left',
                                                       padx=(0, 8))

    if report:
        def _copy_details():
            text = _diagnostics_report(title, msg)
            try:
                top.clipboard_clear()
                top.clipboard_append(text)
                copy_btn.config(text='Copied ✓')
                top.after(1500,
                          lambda: copy_btn.config(text='Copy Details'))
            except Exception as exc:
                _log(f'copy details failed: {exc}')

        copy_btn = tk.Button(btn_row, text='Copy Details', width=14,
                             command=_copy_details)
        copy_btn.pack(side='right')

    if copy_cmd:
        def _copy_command():
            try:
                top.clipboard_clear()
                top.clipboard_append(copy_cmd)
                cmd_btn.config(text='Copied ✓')
                top.after(1500,
                          lambda: cmd_btn.config(text='Copy Command'))
            except Exception as exc:
                _log(f'copy command failed: {exc}')

        cmd_btn = tk.Button(btn_row, text='Copy Command', width=14,
                            command=_copy_command)
        cmd_btn.pack(side='right', padx=(0, 8))

    top.protocol('WM_DELETE_WINDOW', lambda: _pick(buttons[-1][0]))

    # Center over the splash window; fall back to the screen center if the
    # splash is not visible (e.g. already destroyed).
    top.update_idletasks()
    try:
        visible = bool(splash.root.winfo_viewable())
    except Exception:
        visible = False
    if visible:
        px = splash.root.winfo_x() + (splash.W - top.winfo_width()) // 2
        py = splash.root.winfo_y() + (splash.H - top.winfo_height()) // 2
    else:
        px = (top.winfo_screenwidth() - top.winfo_width()) // 2
        py = (top.winfo_screenheight() - top.winfo_height()) // 2
    top.geometry(f'+{max(0, px)}+{max(0, py)}')

    top.grab_set()
    splash.root.wait_window(top)
    _log(f'CHOICE RESULT: {choice["v"]}')
    return choice['v']


# ─────────────────────────────────────────────────────────────────────────────
# Distro detection
# ─────────────────────────────────────────────────────────────────────────────

def _is_utility_distro(name):
    """True for tooling distros (Docker/Rancher/Podman) that can't run the GUI."""
    n = (name or '').strip().lower()
    return n in _UTILITY_DISTROS or n.startswith('podman-machine')


def _registry_default_distro():
    """Read the default distro name from the registry (no localized parsing)."""
    if winreg is None:
        return None
    try:
        base = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows\CurrentVersion\Lxss')
        guid, _ = winreg.QueryValueEx(base, 'DefaultDistribution')
        sub = winreg.OpenKey(base, guid)
        name, _ = winreg.QueryValueEx(sub, 'DistributionName')
        return (name or '').strip() or None
    except OSError:
        return None


def _wsl_list_distros():
    """Return installed distro names, or None if wsl.exe itself is missing.

    `wsl -l -q` emits UTF-16LE on most Windows builds — decode accordingly
    and strip stray NULs.
    """
    try:
        r = subprocess.run(
            [_WSL_EXE, '-l', '-q'],
            capture_output=True,
            timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
    except (FileNotFoundError, OSError):
        return None
    except subprocess.TimeoutExpired:
        return []
    raw = r.stdout or b''
    if b'\x00' in raw:
        text = raw.decode('utf-16-le', errors='replace')
    else:
        text = raw.decode(errors='replace')
    text = text.replace('\x00', '')
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _detect_distro():
    """Pick the distro all WSL commands will target.

    Returns 'ok' (sets module-level _DISTRO), 'no-wsl' (wsl.exe missing) or
    'no-distro' (no usable Linux distro installed).
    """
    global _DISTRO
    distros = _wsl_list_distros()
    if distros is None:
        return 'no-wsl'

    default = _registry_default_distro()
    if default and not _is_utility_distro(default):
        _DISTRO = default
        _log(f'distro: default "{default}"')
        return 'ok'

    candidates = [d for d in distros if not _is_utility_distro(d)]
    for d in candidates:
        if d.lower().startswith('ubuntu'):
            _DISTRO = d
            _log(f'distro: ubuntu-like "{d}" (default was "{default}")')
            return 'ok'
    if candidates:
        _DISTRO = candidates[0]
        _log(f'distro: first usable "{candidates[0]}" (default was "{default}")')
        return 'ok'
    return 'no-distro'


# ─────────────────────────────────────────────────────────────────────────────
# WSL boot / display readiness
# ─────────────────────────────────────────────────────────────────────────────

def _wait_for_wsl(splash):
    """Wait up to _WSL_BOOT_BUDGET_S for the distro to answer `echo ok`.

    The first wsl.exe call after Windows boot starts the whole WSL VM, which
    can take well over 10 seconds on corporate machines — and even when an
    individual attempt times out, the VM keeps booting in the background, so
    retrying is exactly the right move (this is why "restart the device"
    never was the real fix).

    Returns 'ok', 'timeout' or 'no-wsl'.
    """
    start = time.time()
    attempt = 0
    while True:
        attempt += 1
        rc, out, err = _wsl('echo ok', timeout=15)
        if rc == 0 and out == 'ok':
            _log(f'wsl ready after {time.time() - start:.1f}s '
                 f'({attempt} attempt(s))')
            return 'ok'
        if rc == -1:
            return 'no-wsl'
        elapsed = time.time() - start
        _log(f'wsl attempt {attempt} rc={rc} err={err[:120]}')
        if elapsed >= _WSL_BOOT_BUDGET_S:
            return 'timeout'
        remaining = int(_WSL_BOOT_BUDGET_S - elapsed)
        splash.set_status(f'Starting WSL… this can take a minute on first '
                          f'boot ({remaining}s)')
        splash.pump()
        time.sleep(2)


def _restart_wsl(splash):
    """Run `wsl --shutdown` (the user has already confirmed the warning)."""
    _log('wsl --shutdown requested by user')
    splash.set_status('Restarting WSL…')
    splash.pump()
    try:
        subprocess.run([_WSL_EXE, '--shutdown'],
                       capture_output=True, timeout=40,
                       creationflags=_CREATE_NO_WINDOW)
    except Exception as exc:
        _log(f'wsl --shutdown failed: {exc}')
    time.sleep(2)


def _probe_wslg_display(timeout_seconds=_DISPLAY_BUDGET_S, splash=None):
    """Probe whether PyQt5 can actually open a display connection inside WSL.

    Spawns a tiny QApplication and watches for the XCB plugin failure that
    silently kills the GUI on fresh Ubuntu WSL installs.  Retries every
    second so a freshly-warming WSLg compositor has time to come online.

    Returns (status, detail):
        ('ok', None)        — display ready, or PyQt5 not installed yet (the
                              package check + setup will handle that case).
        ('xcb', detail)     — Qt's XCB platform plugin failed: system display
                              libraries are missing; fixable by setup.
        ('timeout', detail) — display never became ready.
    """
    # Single-line Python kept inside double quotes so bash sees one -c arg.
    probe_cmd = (
        'timeout 8 python3 -c '
        '"from PyQt5.QtWidgets import QApplication; '
        'import sys; '
        'app = QApplication(sys.argv); '
        "print('display_ok')\" 2>&1"
    )

    last_output = ''
    start = time.time()
    while True:
        rc, out, err = _wsl(probe_cmd, timeout=12)
        combined = ((out or '') + '\n' + (err or '')).strip()
        last_output = combined
        lowered = combined.lower()

        if 'display_ok' in (out or ''):
            return 'ok', None

        # PyQt5 not installed yet — probe is inconclusive; let the package
        # check + install gate handle it on this (or the next) pass.
        if 'no module named' in lowered or 'modulenotfounderror' in lowered:
            return 'ok', None

        # XCB / Qt plugin failure — missing system libraries; setup fixes it.
        if 'xcb' in lowered or 'platform plugin' in lowered:
            return 'xcb', combined

        elapsed = time.time() - start
        if elapsed >= timeout_seconds:
            return 'timeout', last_output

        if splash is not None:
            remaining = max(0, int(timeout_seconds - elapsed))
            splash.set_status(f'Waiting for display… ({remaining}s)')
            splash.pump()
        time.sleep(1)


# ─────────────────────────────────────────────────────────────────────────────
# WSL / distro install & repair flows
# ─────────────────────────────────────────────────────────────────────────────

def _manual_install_guide(splash, title, what, command, declined):
    """Numbered manual-install instructions shown when an automatic install
    could not run (admin permission declined, blocked by policy, or failed).
    The caller closes the launcher afterwards; on the next run the launcher
    re-checks and continues automatically."""
    if declined:
        intro = (f'{what} needs administrator permission, and the '
                 'permission prompt was declined (or this account does '
                 'not have administrator rights).')
    else:
        intro = (f'{what} could not be completed automatically.')
    _choice_dialog(
        splash, title,
        intro + '\n\n'
        'To finish manually:\n'
        '  1. If this is a company laptop without admin rights, ask your\n'
        '     IT administrator to do steps 2–4 (use "Copy Details" to\n'
        '     include diagnostics in your request).\n'
        '  2. Open PowerShell as Administrator (right-click Start →\n'
        '     "Terminal (Admin)").\n'
        '  3. Run:\n'
        f'       {command}\n'
        '     ("Copy Command" puts it on the clipboard.)\n'
        '  4. Restart the computer if asked to.\n'
        '  5. Run this launcher again — it will detect the install and\n'
        '     continue with the remaining setup automatically.'
        f'\n\nLog: {_LOG_PATH}',
        [('close', 'Close')], report=True, copy_cmd=command)


def _find_paraview():
    """Return the newest installed ParaView paraview.exe path, or None.

    Mirrors ui_shared.find_paraview_exe's glob but stays stdlib-only (the
    launcher must not import PyQt/ui_shared)."""
    matches = glob.glob(r'C:\Program Files\ParaView*\bin\paraview.exe')
    if not matches:
        return None
    # Newest install wins (ParaView-5.12.0 > ParaView-5.11.0).
    return sorted(matches)[-1]


def _check_paraview(splash):
    """Optional, non-blocking soft check for ParaView (Windows-side viewer).

    ParaView is only used to view mesh results in 3D — the app works fine
    without it — so this NEVER fails the launch.  If ParaView is missing a
    single, dismissible dialog offers a download link; a sentinel then
    suppresses the dialog on subsequent launches."""
    path = _find_paraview()
    if path:
        _log(f'ParaView found: {path}')
        return
    if os.path.exists(_PARAVIEW_DECLINED_SENTINEL):
        _log('ParaView not found — dialog already dismissed once, skipping')
        return
    _log('ParaView not found — showing optional download dialog')
    choice = _choice_dialog(
        splash, 'ParaView Not Found (Optional)',
        'ParaView is optional. It is only used to view your mesh\n'
        'results in 3D — the app works fine without it, and you can\n'
        'install it later at any time.\n\n'
        '"Download ParaView" opens the download page in your browser.\n'
        'You can continue launching now either way.',
        [('download', 'Download ParaView'),
         ('continue', 'Continue without it')])
    if choice == 'download':
        _log('ParaView: user chose Download')
        try:
            webbrowser.open('https://www.paraview.org/download/')
        except Exception as exc:
            _log(f'ParaView: webbrowser.open failed: {exc}')
    else:
        _log('ParaView: user chose Continue without it')
    # Remember the dismissal so we never nag on future launches.
    try:
        with open(_PARAVIEW_DECLINED_SENTINEL, 'w', encoding='utf-8') as fh:
            fh.write('1')
    except OSError as exc:
        _log(f'ParaView: could not write sentinel: {exc}')


def _install_wsl(splash):
    """Install the WSL platform itself (elevated, no distro).

    Returns 'ok' (retry checks), 'reboot' (user chose to restart now — the
    caller exits), 'declined' (UAC prompt refused / no admin rights) or
    'fail'.
    """
    rc, out = _run_elevated(
        'wsl.exe', ['--install', '--no-distribution'],
        splash, 'Installing WSL — approve the administrator prompt',
        timeout_s=_WSL_INSTALL_BUDGET_S)
    if rc != 0:
        _log(f'wsl --install rc={rc} out={out[:300]!r}')
        return 'declined' if _is_uac_declined(out) else 'fail'
    # Enabling VirtualMachinePlatform for the first time usually needs one
    # Windows restart before wsl.exe becomes functional.
    choice = _choice_dialog(
        splash, 'WSL Installed — Restart Recommended',
        'WSL was installed. A one-time Windows restart is usually\n'
        'required to finish enabling it.\n\n'
        '"Restart Now" restarts this computer in 5 seconds — save your\n'
        'work in other applications first. After the restart, run this\n'
        'launcher again and it will continue automatically.',
        [('reboot', 'Restart Now'), ('later', 'Continue Without Restart')])
    if choice == 'reboot':
        try:
            subprocess.Popen(['shutdown', '/r', '/t', '5'],
                             creationflags=_CREATE_NO_WINDOW)
        except Exception as exc:
            _log(f'shutdown failed: {exc}')
            return 'fail'
        return 'reboot'
    return 'ok'


def _install_ubuntu(splash):
    """Download/register Ubuntu, then guide the user through first-run
    (UNIX username + password) in a visible terminal.

    Returns 'ok', 'declined' (UAC prompt refused) or 'fail'.
    """
    rc, out = _run_win_streaming(
        [_WSL_EXE, '--install', '-d', 'Ubuntu', '--no-launch'],
        splash, 'Downloading Ubuntu — this can take several minutes',
        timeout_s=_WSL_INSTALL_BUDGET_S)
    if rc != 0:
        lowered = out.lower()
        if 'elevat' in lowered or 'administrator' in lowered:
            rc, out = _run_elevated(
                'wsl.exe', ['--install', '-d', 'Ubuntu', '--no-launch'],
                splash, 'Installing Ubuntu — approve the administrator prompt',
                timeout_s=_WSL_INSTALL_BUDGET_S)
        if rc != 0:
            _log(f'ubuntu install failed: {out[:300]}')
            return 'declined' if _is_uac_declined(out) else 'fail'

    _choice_dialog(
        splash, 'Ubuntu — One-Time Setup',
        'Ubuntu is installed. A terminal window will now open to create\n'
        'your Linux user account:\n\n'
        '  1. Enter a username (lowercase letters, e.g. your first name)\n'
        '  2. Choose a password and type it twice (typing is invisible —\n'
        '     that is normal)\n'
        '  3. When you see the green $ prompt, you can close the terminal\n\n'
        'Remember this password — it is asked for again during setup.',
        [('ok', 'Open Terminal')])

    try:
        subprocess.Popen(['wt.exe', '--', 'wsl', '-d', 'Ubuntu'],
                         creationflags=_CREATE_NO_WINDOW)
    except (FileNotFoundError, OSError):
        try:
            subprocess.Popen(['cmd.exe', '/c', 'start', '',
                              'wsl', '-d', 'Ubuntu'],
                             creationflags=_CREATE_NO_WINDOW)
        except (FileNotFoundError, OSError):
            return 'fail'

    # First-run is done once a real (non-root) user home exists.
    start = time.time()
    while time.time() - start < _FIRSTRUN_BUDGET_S:
        rc, out, _ = _wsl_named('Ubuntu', 'ls /home 2>/dev/null | head -1',
                                timeout=10)
        if rc == 0 and out.strip():
            _log(f'ubuntu first-run done (user {out.strip()!r})')
            return 'ok'
        remaining = int(_FIRSTRUN_BUDGET_S - (time.time() - start))
        splash.set_status('Waiting for Ubuntu account creation — follow '
                          f'the terminal… ({remaining}s)')
        splash.pump()
        time.sleep(3)
    _log('ubuntu first-run timed out')
    return 'fail'


def _wsl_named(distro, cmd, timeout=15):
    """Like _wsl() but targets an explicit distro name."""
    try:
        r = subprocess.run(
            [_WSL_EXE, '-d', distro, '--exec', 'bash', '-c', cmd],
            capture_output=True, text=True, timeout=timeout,
            creationflags=_CREATE_NO_WINDOW)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as exc:
        return -3, '', str(exc)


def _distro_wsl_version(name):
    """Return 1 or 2 for the named distro from `wsl -l -v`, or None."""
    try:
        r = subprocess.run([_WSL_EXE, '-l', '-v'], capture_output=True,
                           timeout=15, creationflags=_CREATE_NO_WINDOW)
    except Exception:
        return None
    for ln in _decode_console(r.stdout).splitlines():
        parts = ln.replace('*', ' ').split()
        if len(parts) >= 3 and parts[0].lower() == (name or '').lower():
            try:
                return int(parts[-1])
            except ValueError:
                return None
    return None


def _convert_to_wsl2(splash):
    """Convert the selected distro from WSL1 to WSL2. Returns True on success."""
    rc, out = _run_win_streaming(
        [_WSL_EXE, '--set-version', _DISTRO, '2'],
        splash, f'Converting {_DISTRO} to WSL2 — this can take a while',
        timeout_s=_CONVERT_BUDGET_S)
    if rc != 0:
        _log(f'set-version failed: {out[:300]}')
    return rc == 0


def _wsl_update(splash):
    """Run `wsl --update` then `wsl --shutdown`. Returns True on success."""
    rc, out = _run_win_streaming(
        [_WSL_EXE, '--update'],
        splash, 'Updating WSL', timeout_s=600)
    if rc != 0:
        _log(f'wsl --update failed: {out[:300]}')
        return False
    _restart_wsl(splash)
    return True


def _probe_network(need_openfoam):
    """TCP-reachability check for the hosts setup will download from.

    Uses bash's /dev/tcp (no curl/wget dependency on fresh images).
    Returns a list of unreachable host names (empty = all fine).
    """
    hosts = [('archive.ubuntu.com', 80)]
    if need_openfoam:
        hosts.append(('dl.openfoam.com', 443))
    blocked = []
    for host, port in hosts:
        rc, out, _ = _wsl(
            f'timeout 6 bash -c "exec 3<>/dev/tcp/{host}/{port}" '
            f'2>/dev/null && echo ok || echo blocked',
            timeout=12)
        if out.strip() != 'ok':
            blocked.append(host)
            _log(f'network probe: {host}:{port} unreachable')
    return blocked


def _check_disk_space(need_openfoam):
    """Return a warning string if free space looks too small, else ''."""
    need_gb = _DISK_NEED_OPENFOAM_GB if need_openfoam else _DISK_NEED_BASE_GB
    problems = []
    rc, out, _ = _wsl("df -k --output=avail / | tail -1", timeout=10)
    if rc == 0 and out.strip().isdigit():
        free_gb = int(out.strip()) / (1024 * 1024)
        if free_gb < need_gb:
            problems.append(
                f'Linux (WSL) disk: {free_gb:.1f} GB free, '
                f'about {need_gb} GB needed')
    try:
        import shutil
        free_gb = shutil.disk_usage('C:\\').free / (1024 ** 3)
        if free_gb < need_gb:
            problems.append(
                f'Windows C: drive: {free_gb:.1f} GB free, '
                f'about {need_gb} GB needed (WSL storage lives on C:)')
    except Exception:
        pass
    return '\n'.join(problems)


# ─────────────────────────────────────────────────────────────────────────────
# Interactive install flow
# ─────────────────────────────────────────────────────────────────────────────

def _detect_openfoam_bashrc():
    """Detect which OpenFOAM bashrc is available — prefer 2506, fall back to
    2312.  Updates the module-level _DETECTED_BASHRC and returns it (or None
    if neither version is installed).

    NOTE: the pre-flight happy path no longer calls this (the merged probe
    in _do_checks covers it in one WSL round trip); kept for repair flows.
    """
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


def _status_capture(component):
    """Bash lines that record the previous command's exit code for one
    setup component into the temp status file."""
    return [
        'rc=$?',
        f'if [ $rc -eq 0 ]; then echo "{component}=ok" >> "$STATUS_TMP"; '
        f'else echo "{component}=fail:$rc" >> "$STATUS_TMP"; fi',
        'echo ""',
        '',
    ]


def _build_setup_script(install_openfoam, apt_packages):
    """Build the bash setup script body as a single string.

    apt-only by design: fresh Ubuntu WSL images have no pip3, and pip's
    --break-system-packages flag does not exist before Ubuntu 23.04 — the
    old pip-based script failed on both counts while still touching the
    sentinel, which made the launcher loop the install popup forever.

    Always runs `apt-get update` first (fresh images have stale/empty
    package lists) and always installs the Qt/XCB system libraries (every
    fresh Ubuntu WSL install needs them for PyQt5 to display).  Optionally
    installs OpenFOAM 2506 and any missing apt packages (python3-pyqt5,
    python3-numpy, …) in the same transaction as the Qt libraries.

    Each section appends `component=ok` or `component=fail:<rc>` to a temp
    status file which is mv'd onto the sentinel as the script's last action,
    so the sentinel appears atomically, only when the script completed, and
    carries the truth about what succeeded.

    `set -e` is intentionally NOT used — every section must run to
    completion so the sentinel is always written and the user sees every
    error in the terminal.
    """
    qt_libs = (
        '  libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \\\n'
        '  libxcb-randr0 libxcb-render-util0 libxcb-xinerama0 \\\n'
        '  libxcb-xfixes0 libxcb-cursor0 libxkbcommon-x11-0 \\\n'
        '  libxcb-shape0 libxcb-util1 \\\n'
        '  libegl1 libgl1 libglib2.0-0 \\\n'
        '  libdbus-1-3 libfontconfig1 libfreetype6 \\\n'
        '  x11-utils \\\n'
        # Nimbus Sans — metrically Helvetica-compatible. The GUI asks for
        # "Helvetica" (ui_shared.FONT_UI); without this, fontconfig silently
        # substitutes DejaVu Sans. Not required to run, only to look right.
        '  fonts-urw-base35'
    )
    extra = ''
    if apt_packages:
        extra = ' \\\n  ' + ' '.join(apt_packages)

    lines = [
        '#!/usr/bin/env bash',
        f'STATUS_TMP="$HOME/.openfoam_ui_setup_status.tmp"',
        f'SENTINEL="$HOME/.openfoam_ui_setup_done"',
        'rm -f "$SENTINEL" "$STATUS_TMP"',
        ': > "$STATUS_TMP"',
        'echo "============================================"',
        'echo " OpenFOAM GUI — First-Time Setup"',
        'echo "============================================"',
        'echo ""',
        '',
        'echo "=== Updating package lists (apt-get update) ==="',
        'sudo apt-get update',
    ]
    lines.extend(_status_capture('aptupdate'))
    lines.extend([
        'echo "=== Installing display libraries and Python packages ==="',
        'sudo apt-get install -y \\',
        qt_libs + extra,
    ])
    lines.extend(_status_capture('packages'))
    if install_openfoam:
        lines.extend([
            'echo "=== Installing OpenFOAM 2506 ==="',
            # -f makes curl fail on HTTP errors instead of piping an HTML
            # error page into bash; download-then-run keeps the chain's exit
            # code meaningful for the status capture below.
            'curl -fsSL -o /tmp/openfoam_add_repo.sh '
            'https://dl.openfoam.com/add-debian-repo.sh \\',
            '  && sudo bash /tmp/openfoam_add_repo.sh \\',
            '  && sudo apt-get update \\',
            '  && sudo apt-get install -y openfoam2506',
        ])
        lines.extend(_status_capture('openfoam'))
    lines.extend([
        'echo "=== Verifying PyQt5 display connection ==="',
        'if python3 -c "',
        'from PyQt5.QtWidgets import QApplication',
        'import sys',
        'app = QApplication(sys.argv)',
        "print('PyQt5 display: OK')",
        'sys.exit(0)',
        '" 2>&1; then',
        '    echo "display=ok" >> "$STATUS_TMP"',
        '    echo "Display verification passed."',
        'else',
        '    echo "display=warn" >> "$STATUS_TMP"',
        '    echo ""',
        '    echo "WARNING: PyQt5 could not connect to the display."',
        '    echo "This may resolve itself after a WSL restart."',
        '    echo "If the GUI does not appear after launch, run:"',
        '    echo "  wsl --shutdown"',
        '    echo "  then relaunch OpenFOAM_UI.exe"',
        '    echo ""',
        'fi',
        'echo ""',
        '',
        'echo "============================================"',
        'echo " Setup finished."',
        'echo "============================================"',
        'mv "$STATUS_TMP" "$SENTINEL"',
        'read -p "Press Enter to close this window..."',
    ])
    return '\n'.join(lines) + '\n'


def _write_setup_script(install_openfoam, apt_packages):
    """Write the setup script into the WSL home directory via base64.

    Returns True if the WSL command succeeded, False otherwise.
    """
    body = _build_setup_script(install_openfoam, apt_packages)
    b64 = base64.b64encode(body.encode()).decode()
    rc, _, _ = _wsl(
        f'echo "{b64}" | base64 -d > {_SETUP_SCRIPT_WSL} && '
        f'chmod +x {_SETUP_SCRIPT_WSL}',
        timeout=15,
    )
    return rc == 0


def _parse_setup_status(text):
    """Parse `component=value` sentinel lines into an ordered dict."""
    status = {}
    for ln in (text or '').splitlines():
        if '=' in ln:
            k, v = ln.split('=', 1)
            status[k.strip()] = v.strip()
    return status


def _describe_setup_failures(status):
    """Build a user-facing description of failed setup components.

    Returns '' when nothing failed (display=warn is informational only —
    the launcher re-probes the display itself on the next check pass).
    """
    parts = []
    for comp, val in status.items():
        if not val.startswith('fail'):
            continue
        rc = val.split(':', 1)[1] if ':' in val else '?'
        label, fix, hint = _FAIL_INFO.get(
            comp, (comp, '(see terminal output)', ''))
        block = f'• {label} failed (exit code {rc}).\n  Fix manually in a WSL terminal:\n    {fix}'
        if hint:
            block += f'\n  {hint}'
        parts.append(block)
    return '\n\n'.join(parts)


def _launch_install_terminal(splash):
    """Launch the setup script in a visible terminal and wait for it to finish.

    Strategy:
      1. Clear stale sentinel.
      2. Try Windows Terminal (wt.exe) first, fall back to cmd.exe.
         Both are launched with CREATE_NO_WINDOW so the launcher itself
         doesn't spawn a console; the terminal app shows its own window.
         Both target the detected distro explicitly via `wsl -d`.
      3. Poll the sentinel file (mv'd into place as the script's last
         action) every 2 seconds, up to 30 minutes.  After a 20 s startup
         grace period, also watch for the bash script disappearing without
         writing the sentinel (user closed the terminal early); require 3
         consecutive "gone" readings to avoid false positives during apt's
         brief lulls.

    proc.wait() is deliberately NOT called: wt.exe and `cmd /c start` both
    fork off the terminal and exit immediately, so the only authoritative
    completion signal is the sentinel.

    Returns the sentinel's text content on completion, or None if the
    terminal closed early / timed out.
    """
    # Clear any sentinel from a previous attempt so we don't mistake it for
    # success on this attempt.
    _wsl(f'rm -f {_SETUP_SENTINEL_WSL} {_SETUP_STATUS_TMP_WSL}', timeout=5)

    distro_args = ['-d', _DISTRO] if _DISTRO else []
    proc = None
    try:
        proc = subprocess.Popen(
            ['wt.exe', '--',
             'wsl', *distro_args, 'bash', _SETUP_SCRIPT_WSL],
            creationflags=_CREATE_NO_WINDOW,
        )
        _log('setup terminal: wt.exe')
    except (FileNotFoundError, OSError):
        try:
            proc = subprocess.Popen(
                ['cmd.exe', '/c', 'start', '',
                 'wsl', *distro_args, 'bash', '-c',
                 f'bash {_SETUP_SCRIPT_WSL}'],
                creationflags=_CREATE_NO_WINDOW,
            )
            _log('setup terminal: cmd.exe fallback')
        except (FileNotFoundError, OSError):
            return None

    if proc is None:
        return None

    splash.set_status(
        'Setup running — follow the prompts in the terminal window…'
    )

    max_iterations = 1800        # 30 min ÷ 2 s
    grace_iterations = 10        # 20 s before we start watching pgrep
    gone_streak = 0

    for i in range(max_iterations):
        splash.pump()
        time.sleep(2)

        # Primary completion signal — sentinel file with status content.
        rc, out, _ = _wsl(
            f'cat {_SETUP_SENTINEL_WSL} 2>/dev/null',
            timeout=5,
        )
        if rc == 0 and out.strip():
            _log(f'setup sentinel: {out.strip()!r}')
            return out

        # Secondary signal — script process disappeared without writing the
        # sentinel (user closed the terminal early).  The [o] bracket stops
        # pgrep -f from matching this polling command's own command line.
        # Only enforced after the startup grace window so we don't
        # false-positive while WSL is still booting.
        if i >= grace_iterations:
            rc, out, _ = _wsl(
                "pgrep -f '[o]penfoam_ui_setup.sh' > /dev/null && "
                'echo running || echo gone',
                timeout=5,
            )
            if out.strip() == 'gone':
                gone_streak += 1
                if gone_streak >= 3:
                    _log('setup terminal closed early')
                    return None
            else:
                gone_streak = 0

    _log('setup polling timed out (30 min)')
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Pre-flight checks
# ─────────────────────────────────────────────────────────────────────────────

def _do_checks(splash, consent_given, install_attempts):
    """Run a single pass of pre-flight checks.

    Returns one of:
      ('ok',)                              — ready to launch.
      ('fatal', title, message)            — unrecoverable; caller shows the
                                             dialog and exits.
      ('retry', title, message, allow_wsl_restart)
                                           — recoverable; caller offers
                                             [Try Again] (+ [Restart WSL]).
      ('install-ok',)                      — setup ran and reported success;
                                             caller re-runs checks.
      ('install-fail', title, message)     — setup ran but something failed;
                                             caller offers [Run Setup Again].
    """
    n = 8
    step = [0]

    def tick(label):
        step[0] += 1
        splash.set_status(label)
        splash.set_progress(step[0] / n)
        _log(f'step: {label}')

    # ── Step 0: Windows build gate (WSLg needs 21362+) ──────────────────────
    build = _windows_build()
    if build is not None and build < _MIN_WSLG_BUILD:
        return 'fatal', 'Windows Version Too Old', (
            f'This Windows build ({build}) does not support WSLg, which\n'
            'the GUI needs to display Linux windows.\n\n'
            'Requirement: Windows 11, or Windows 10 build 21362 or later.\n\n'
            'Update Windows, then run this launcher again.'
        )

    # ── Step 1: pick a distro ────────────────────────────────────────────────
    tick('Detecting WSL distribution…')
    distro_state = _detect_distro()
    if distro_state == 'no-wsl':
        return 'install-wsl', 'WSL Not Installed', (
            'WSL (Windows Subsystem for Linux) is not installed on this\n'
            'machine. The GUI runs inside WSL, so it is required.\n\n'
            '"Install WSL" below installs it for you — you will see an\n'
            'administrator (UAC) prompt, and a one-time Windows restart\n'
            'may be needed afterwards.\n\n'
            'Contact your IT administrator if the install is blocked by '
            'policy.'
        )
    if distro_state == 'no-distro':
        return 'install-distro', 'No Linux Distribution Found', (
            'WSL is installed but no usable Linux distribution was found\n'
            '(Docker/Rancher utility distros cannot run the GUI).\n\n'
            '"Install Ubuntu" below downloads Ubuntu and walks you\n'
            'through creating a Linux user account (a few minutes).'
        )

    # ── Step 2: WSL reachable (patient — boots the VM if cold) ──────────────
    tick('Starting WSL…')
    boot = _wait_for_wsl(splash)
    if boot == 'no-wsl':
        return 'fatal', 'WSL Not Found', (
            'wsl.exe disappeared from PATH while starting.\n\n'
            'Fix: reinstall WSL2 from PowerShell (run as Administrator):\n'
            '  wsl --install'
        )
    if boot == 'timeout':
        return 'retry', 'WSL Did Not Start', (
            f'WSL did not respond within {_WSL_BOOT_BUDGET_S} seconds.\n\n'
            f'Distribution: {_DISTRO}\n\n'
            'WSL may be stuck. "Restart WSL" below runs wsl --shutdown\n'
            'and tries again — no need to restart your computer.'
        ), True

    # ── Step 2b: WSL1 distros can't run WSLg — offer conversion ─────────────
    wsl_ver = _distro_wsl_version(_DISTRO)
    if wsl_ver == 1:
        return 'convert-wsl1', 'Distribution Uses WSL1', (
            f'The Linux distribution "{_DISTRO}" runs under WSL1, which\n'
            'cannot display GUI windows (no WSLg support).\n\n'
            '"Convert to WSL2" below upgrades it in place. This can take\n'
            'several minutes and the distribution is unavailable while it\n'
            'runs, but no files are lost.'
        )

    # ── Steps 3–5 (one WSL call): display env + OpenFOAM bashrc + python3
    # + package check.  Each wsl.exe spawn costs 150–400 ms and the package
    # loop imports PyQt5, so folding four sequential probes into a single
    # bash script saves seconds on every full-check run.  Output is one
    # KEY=value line per probe, parsed below.
    tick('Checking WSLg display…')
    imports = ' '.join(imp for imp, _ in _REQUIRED_PACKAGES)
    probe_script = (
        'printf "DISP=%s%s\\n" "$DISPLAY" "$WAYLAND_DISPLAY"; '
        f'if test -f {_FOAM_BASHRC_2506}; then printf "FOAM=2506\\n"; '
        f'elif test -f {_FOAM_BASHRC_2312}; then printf "FOAM=2312\\n"; '
        'else printf "FOAM=none\\n"; fi; '
        'if command -v python3 >/dev/null 2>&1; then printf "PY=yes\\n"; '
        f'miss=""; for p in {imports}; do '
        'python3 -c "import $p" 2>/dev/null || miss="$miss $p"; done; '
        'printf "MISS=%s\\n" "$miss"; '
        'else printf "PY=no\\n"; printf "MISS=\\n"; fi'
    )

    probe_vals = {}
    env_deadline = time.time() + 15
    while True:
        rc, out, _ = _wsl(probe_script, timeout=25)
        if rc == 0:
            probe_vals = dict(
                ln.split('=', 1) for ln in out.splitlines() if '=' in ln)
            if probe_vals.get('DISP', '').strip():
                break
        if time.time() >= env_deadline:
            break
        splash.set_status('Waiting for WSLg display environment…')
        splash.pump()
        time.sleep(2)
    if not probe_vals.get('DISP', '').strip():
        return 'retry-update', 'No Display Available', (
            'Neither $DISPLAY nor $WAYLAND_DISPLAY is set inside WSL.\n\n'
            'The GUI requires WSLg (Windows Subsystem for Linux GUI).\n'
            'An outdated WSL is the usual cause.\n\n'
            '"Update WSL" below runs wsl --update and restarts WSL —\n'
            'this usually fixes it, no computer restart needed.\n\n'
            'Contact your IT administrator if the problem persists.'
        )

    # ── Step 3b: WSLg compositor readiness ──────────────────────────────────
    tick('Waiting for display server…')
    probe, probe_detail = _probe_wslg_display(splash=splash)
    xcb_broken = (probe == 'xcb')
    if probe == 'timeout':
        return 'retry', 'Display Not Ready', (
            f'The WSLg display server did not become ready within '
            f'{_DISPLAY_BUDGET_S} seconds.\n\n'
            '"Restart WSL" below usually fixes this — no need to restart\n'
            'your computer.\n\n'
            f'Technical detail: '
            f'{probe_detail[:200] if probe_detail else "(none)"}'
        ), True
    if xcb_broken:
        _log(f'xcb probe failed — will install display libraries: '
             f'{(probe_detail or "")[:200]}')

    # ── Steps 4–5: interpret the merged probe (no further WSL calls) ─────────
    tick('Checking OpenFOAM installation…')
    global _DETECTED_BASHRC
    foam = probe_vals.get('FOAM', 'none')
    _DETECTED_BASHRC = {'2506': _FOAM_BASHRC_2506,
                        '2312': _FOAM_BASHRC_2312}.get(foam)
    install_openfoam = _DETECTED_BASHRC is None

    tick('Checking Python packages…')
    python3_missing = probe_vals.get('PY') != 'yes'
    if python3_missing:
        missing = [imp for imp, _ in _REQUIRED_PACKAGES]
    else:
        missing = probe_vals.get('MISS', '').strip().split()

    # ── Step 6: Interactive install gate ─────────────────────────────────────
    tick('Reviewing installation requirements…')
    need_setup = install_openfoam or missing or python3_missing or xcb_broken
    if need_setup:
        apt_to_imp = {apt: imp for imp, apt in _REQUIRED_PACKAGES}
        imp_to_apt = {imp: apt for imp, apt in _REQUIRED_PACKAGES}
        apt_packages = []
        if python3_missing:
            apt_packages.append('python3')
        apt_packages += [imp_to_apt[m] for m in missing if m in imp_to_apt]

        if install_attempts >= 2:
            still = []
            if install_openfoam:
                still.append('  • OpenFOAM 2506')
            still += [f'  • {p}' for p in apt_packages]
            if xcb_broken:
                still.append('  • Qt display libraries')
            return 'install-fail', 'Setup Did Not Fix the Problem', (
                'Setup ran but these components are still not working:\n\n'
                + '\n'.join(still) + '\n\n'
                'Open a WSL terminal and install them manually:\n'
                '  sudo apt-get update\n'
                '  sudo apt-get install -y python3-pyqt5 python3-numpy python3-jinja2\n'
                '  sudo apt-get install -y openfoam2506   # if OpenFOAM '
                'is listed above\n\n'
                'Then run this launcher again.'
            )

        bullets = []
        if install_openfoam:
            bullets.append('  • OpenFOAM 2506 (required for mesh generation)')
        bullets.append('  • Qt display libraries (required by the GUI)')
        if python3_missing:
            bullets.append('  • Python 3')
        for m in missing:
            apt = imp_to_apt.get(m)
            bullets.append(f'  • {m}' + (f'  ({apt})' if apt else ''))
        items = '\n'.join(bullets)

        # Fail fast, with the real reason, before opening the setup terminal:
        # a blocked mirror or a full disk otherwise surfaces minutes into apt.
        splash.set_status('Checking network and disk space…')
        splash.pump()
        blocked = _probe_network(install_openfoam)
        if blocked:
            hosts = '\n'.join(f'  • {h}' for h in blocked)
            go = _choice_dialog(
                splash, 'Download Servers Unreachable',
                'Setup needs to download packages, but these servers are\n'
                'not reachable from WSL:\n\n'
                f'{hosts}\n\n'
                'A corporate proxy or firewall is the usual cause —\n'
                'contact IT, or connect to a different network.\n\n'
                'You can still try anyway (it will fail if the servers\n'
                'really are blocked).',
                [('cancel', 'Cancel Setup'), ('anyway', 'Try Anyway')],
                report=True)
            if go == 'cancel':
                return 'fatal', 'Setup Cancelled', (
                    'Setup was cancelled because the download servers are\n'
                    'unreachable. Run the launcher again once the network\n'
                    'issue is resolved.'
                )
        disk_msg = _check_disk_space(install_openfoam)
        if disk_msg:
            go = _choice_dialog(
                splash, 'Low Disk Space',
                'There may not be enough free disk space for setup:\n\n'
                f'{disk_msg}\n\n'
                'Free up space, or continue anyway at your own risk.',
                [('cancel', 'Cancel Setup'), ('anyway', 'Continue Anyway')])
            if go == 'cancel':
                return 'fatal', 'Setup Cancelled', (
                    'Setup was cancelled due to low disk space. Free up\n'
                    'space and run the launcher again.'
                )

        if not consent_given:
            ok = _ask_yes_no(
                splash,
                'First-Time Setup Required',
                (
                    'The following components need to be installed in WSL:\n\n'
                    f'{items}\n\n'
                    'A terminal window will open — enter your Linux (sudo)\n'
                    'password when prompted. Everything else is automatic.\n\n'
                    'Install now?'
                ),
            )
            if not ok:
                return 'fatal', 'Setup Required', (
                    'These components must be installed before the GUI '
                    'can start:\n\n'
                    f'{items}\n\n'
                    'Run the launcher again when you are ready to install.'
                )

        if not _write_setup_script(install_openfoam, apt_packages):
            return 'retry', 'Setup Script Failed', (
                'Failed to write the setup script to '
                '~/openfoam_ui_setup.sh inside WSL.\n\n'
                'WSL may be in a bad state — "Restart WSL" below and\n'
                'try again.'
            ), True

        splash.set_status('Waiting for setup to complete…')
        sentinel_text = _launch_install_terminal(splash)
        if sentinel_text is None:
            return 'install-fail', 'Setup Did Not Finish', (
                'The setup terminal closed before setup completed.\n\n'
                'No components may have been installed yet.\n\n'
                'Click "Run Setup Again" to reopen the setup terminal —\n'
                'keep it open until it says "Setup finished."'
            )

        failures = _describe_setup_failures(_parse_setup_status(sentinel_text))
        if failures:
            return 'install-fail', 'Setup Completed With Errors', (
                'Setup ran, but not everything installed correctly:\n\n'
                f'{failures}\n\n'
                'You can also click "Run Setup Again" to retry the '
                'installation.'
            )
        return ('install-ok',)

    # ── Step 7: openfoam_ui.py present ───────────────────────────────────────
    tick('Checking application files…')
    ui_py = os.path.join(_get_exe_dir(), 'openfoam_ui.py')
    if not os.path.isfile(ui_py):
        return 'fatal', 'Application File Missing', (
            f'openfoam_ui.py was not found next to the launcher:\n'
            f'  {ui_py}\n\n'
            'Make sure OpenFOAM_UI.exe and all .py files remain\n'
            'together in the same app folder — do not move the\n'
            '.exe out on its own.'
        )

    return ('ok',)


def _run_checks(splash):
    """Drive _do_checks in a retry loop until success or the user gives up.

    Every recoverable failure offers [Try Again] (and [Restart WSL] where
    WSL state could be the cause) so the user never has to relaunch the
    exe — let alone restart the machine.
    """
    consent_given = False
    install_attempts = 0

    while True:
        result = _do_checks(splash, consent_given, install_attempts)
        kind = result[0]

        if kind == 'ok':
            # Optional, non-blocking soft check — runs only after every
            # required environment check has passed, and never fails launch.
            _check_paraview(splash)
            return True

        if kind == 'fatal':
            _show_error(splash, result[1], result[2])
            return False

        if kind == 'install-wsl':
            choice = _choice_dialog(
                splash, result[1], result[2] + f'\n\nLog: {_LOG_PATH}',
                [('install', 'Install WSL'), ('close', 'Close')],
                report=True)
            if choice != 'install':
                return False
            outcome = _install_wsl(splash)
            if outcome == 'reboot':
                return False          # machine is restarting
            if outcome in ('declined', 'fail'):
                _manual_install_guide(
                    splash,
                    'Administrator Permission Needed'
                    if outcome == 'declined' else 'WSL Install Failed',
                    'Installing WSL', 'wsl --install',
                    declined=(outcome == 'declined'))
                return False
            splash.set_progress(0.0)
            continue

        if kind == 'install-distro':
            choice = _choice_dialog(
                splash, result[1], result[2] + f'\n\nLog: {_LOG_PATH}',
                [('install', 'Install Ubuntu'), ('close', 'Close')],
                report=True)
            if choice != 'install':
                return False
            outcome = _install_ubuntu(splash)
            if outcome != 'ok':
                _manual_install_guide(
                    splash,
                    'Administrator Permission Needed'
                    if outcome == 'declined'
                    else 'Ubuntu Install Did Not Finish',
                    'Installing Ubuntu', 'wsl --install -d Ubuntu',
                    declined=(outcome == 'declined'))
                return False
            splash.set_progress(0.0)
            continue

        if kind == 'convert-wsl1':
            choice = _choice_dialog(
                splash, result[1], result[2] + f'\n\nLog: {_LOG_PATH}',
                [('convert', 'Convert to WSL2'), ('close', 'Close')],
                report=True)
            if choice != 'convert':
                return False
            if not _convert_to_wsl2(splash):
                _manual_install_guide(
                    splash, 'Conversion Failed',
                    f'Converting "{_DISTRO}" to WSL2',
                    f'wsl --set-version {_DISTRO} 2',
                    declined=False)
                return False
            splash.set_progress(0.0)
            continue

        if kind == 'retry-update':
            _, title, msg = result
            choice = _choice_dialog(
                splash, title, msg + f'\n\nLog: {_LOG_PATH}',
                [('update', 'Update WSL'), ('retry', 'Try Again'),
                 ('close', 'Close')],
                report=True)
            if choice == 'update':
                if not _wsl_update(splash):
                    _show_error(splash, 'WSL Update Failed', (
                        'wsl --update did not complete.\n\n'
                        'Try manually from PowerShell:\n'
                        '  wsl --update\n\n'
                        'Contact your IT administrator if updates are '
                        'blocked by policy.'
                    ))
                splash.set_progress(0.0)
                continue
            if choice == 'retry':
                splash.set_progress(0.0)
                continue
            return False

        if kind == 'install-ok':
            consent_given = True
            install_attempts += 1
            splash.set_status('Setup complete — re-running checks…')
            splash.set_progress(0.0)
            continue

        if kind == 'install-fail':
            choice = _choice_dialog(
                splash, result[1],
                result[2] + f'\n\nLog: {_LOG_PATH}',
                [('again', 'Run Setup Again'), ('close', 'Close')],
                report=True)
            if choice == 'again':
                consent_given = True
                install_attempts += 1
                splash.set_progress(0.0)
                continue
            return False

        if kind == 'retry':
            _, title, msg, allow_restart = result
            buttons = [('retry', 'Try Again')]
            if allow_restart:
                buttons.append(('restart', 'Restart WSL'))
            buttons.append(('close', 'Close'))
            choice = _choice_dialog(
                splash, title, msg + f'\n\nLog: {_LOG_PATH}', buttons,
                report=True)
            if choice == 'retry':
                splash.set_progress(0.0)
                continue
            if choice == 'restart':
                confirmed = _ask_yes_no(
                    splash, 'Restart WSL?',
                    'This stops ALL running WSL programs (terminals,\n'
                    'Docker containers, running mesh jobs).\n\n'
                    'Your Windows applications are not affected and the\n'
                    'computer will NOT restart.\n\n'
                    'Restart WSL now?',
                    icon='warning')
                if confirmed:
                    _restart_wsl(splash)
                splash.set_progress(0.0)
                continue
            return False


def main():
    """Show the splash, run pre-flight checks, then launch openfoam_ui.py inside WSL."""
    global _DISTRO, _DETECTED_BASHRC
    # Keep the diagnostic log from growing without bound.
    try:
        if (os.path.exists(_LOG_PATH)
                and os.path.getsize(_LOG_PATH) > 512 * 1024):
            os.remove(_LOG_PATH)
    except Exception:
        pass
    _log('───── launcher start ─────')

    # Single instance: GUI already open → focus it and leave; another
    # launcher still starting up → leave silently (its splash is visible).
    if _focus_existing_gui():
        _log('GUI already running — focused existing window, exiting')
        return
    if not _acquire_instance_mutex():
        _log('another launcher is already starting — exiting')
        return

    splash = _Splash()

    # Fast path: the last run passed every check AND the GUI came up, so skip
    # the full chain — boot WSL if needed, then one combined validation call
    # (bashrc still there + PyQt5 still importable).  Any miss falls back to
    # the full self-healing checks and clears the sentinel.
    fastpath_ok = False
    fast = _load_fastpath()
    if fast:
        _DISTRO = fast['distro']
        _DETECTED_BASHRC = fast['bashrc']
        splash.set_status('Starting…')
        splash.set_progress(0.3)
        if _wait_for_wsl(splash) == 'ok':
            rc, out, _ = _wsl(
                f"test -f '{_DETECTED_BASHRC}' "
                "&& python3 -c 'import PyQt5' && echo ok",
                timeout=25)
            if (rc == 0 and out.strip() == 'ok'
                    and os.path.isfile(
                        os.path.join(_get_exe_dir(), 'openfoam_ui.py'))):
                fastpath_ok = True
                _log('fast path: full checks skipped')
        if not fastpath_ok:
            _clear_fastpath()
            _DISTRO = None
            _DETECTED_BASHRC = None
            splash.set_progress(0.0)

    if not fastpath_ok and not _run_checks(splash):
        splash.close()
        sys.exit(1)

    splash.set_status('Launching application…')
    splash.set_progress(1.0)
    time.sleep(0.4)

    # Prefer the bashrc that pre-flight detected; fall back defensively.
    bashrc = _DETECTED_BASHRC or _FOAM_BASHRC_2506
    exe_dir = _get_exe_dir()
    wsl_dir = windows_path_to_wsl(exe_dir)

    # Redirect the GUI's stdout/stderr to a file inside WSL so a silent
    # XCB crash leaves evidence behind for the watchdog to read back.
    log_path_wsl = '/tmp/openfoam_ui_launch.log'

    # Ready sentinel lives on the WINDOWS side (%TEMP%): the GUI writes it
    # through /mnt/c, and the watchdog below checks os.path.exists — a free
    # local stat instead of spawning wsl.exe every 200 ms.
    ready_path_win = os.path.join(tempfile.gettempdir(), 'openfoam_ui_ready')
    try:
        # Clear any stale ready-sentinel from a previous run so we don't
        # false-positive an instant close on a GUI that hasn't started yet.
        os.remove(ready_path_win)
    except OSError:
        pass
    ready_path_wsl = windows_path_to_wsl(ready_path_win)

    launch_cmd = (
        f"source '{bashrc}' && "
        f"cd '{wsl_dir}' && "
        f"OPENFOAM_UI_READY_FILE='{ready_path_wsl}' "
        f"python3 '{wsl_dir}/openfoam_ui.py' "
        f"> {log_path_wsl} 2>&1"
    )

    distro_args = ['-d', _DISTRO] if _DISTRO else []
    try:
        proc = subprocess.Popen(
            [_WSL_EXE, *distro_args, '--exec', 'bash', '-c', launch_cmd],
            creationflags=_CREATE_NO_WINDOW,
        )
        _log(f'GUI launched (distro={_DISTRO})')
    except Exception as exc:
        _show_error(splash, 'Launch Failed', (
            f'Could not start the GUI process:\n\n{exc}\n\n'
            'Try launching manually from a WSL terminal:\n'
            f'  source {bashrc}\n'
            f'  python3 {wsl_dir}/openfoam_ui.py'
        ))
        splash.close()
        sys.exit(1)

    # Watchdog: poll at 200 ms granularity for up to 30 s.  Close the splash
    # the instant the GUI signals readiness (sentinel file appears) so it
    # doesn't linger after the window is mapped.  If the process exits before
    # that, show a crash dialog with the log tail.
    splash.set_status('Starting GUI…')
    max_iterations = 150      # 150 × 0.2 s = 30 s ceiling
    for _ in range(max_iterations):
        time.sleep(0.2)
        splash.pump()

        ret = proc.poll()
        if ret is not None:
            _, log_out, _ = _wsl(
                f'cat {log_path_wsl} 2>/dev/null || echo "(no log)"',
                timeout=5,
            )
            _log(f'GUI exited immediately (code {ret})')
            _clear_fastpath()   # next run re-proves the environment
            xcb_hint = ''
            lowered = (log_out or '').lower()
            if 'xcb' in lowered or 'platform plugin' in lowered:
                xcb_hint = (
                    '\n\nThis looks like a missing display library.\n'
                    'Run this launcher again — it will detect the problem\n'
                    'and offer to install the missing libraries.'
                )
            _show_error(splash, 'GUI Failed to Start', (
                f'The GUI exited immediately (code {ret}).\n\n'
                f'Error output:\n{log_out[:600] if log_out else "(none)"}'
                f'{xcb_hint}'
            ))
            splash.close()
            sys.exit(1)

        # Ready signal — GUI window is mapped; close splash immediately.
        # Local stat on the Windows temp file — no wsl.exe spawn per poll.
        if os.path.exists(ready_path_win):
            _log('GUI ready')
            _save_fastpath()    # this run proved the whole chain works
            break

    splash.close()


if __name__ == '__main__':
    main()



























