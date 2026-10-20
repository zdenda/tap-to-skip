"""
Tap to skip  -  Pixel Buds A double tap -> skip the YouTube ad (Windows)

Runs in the system tray. A DOUBLE tap on the buds (the "next track"
gesture) is caught and turned into a mouse click. A single tap
(play/pause) is never touched.

Modes
-----
1. No skip.png next to the program:
   double tap  ->  left click at the current cursor position.

2. skip.png present (a tight crop of the Skip button's text and icon):
   double tap  ->  search the screen for skip.png for up to SEARCH_SECONDS
                   and click its centre when found. Nothing is clicked if
                   the button never appears.

   Automatic mode (on by default, needs skip.png): every AUTO_INTERVAL
   seconds the program checks the screen by itself and clicks the Skip
   button when it is there. To stay out of your way it only does so when
   the mouse and keyboard have been idle for AUTO_IDLE_SECONDS (taps on
   the buds and the program's own clicks do not count as activity) and
   the active window's title contains "YouTube".

Tray menu
---------
Paused               stop reacting to double taps (they skip tracks again)
                     and stop automatic mode
Automatic mode       automatic clicking on/off (remembered in tap_to_skip.ini)
Start with Windows   start automatically when you sign in
Test skip.png        wait 5 s, take a screenshot, show the match score,
                     the active window's title and the idle time
Reload skip.png      pick up a changed skip.png without restarting
Quit

Command line:  tap_to_skip.exe --test   (the test only, then exit)

Files: tap_to_skip.log and tap_to_skip.ini next to the program (or in the
TapToSkip folder inside %LOCALAPPDATA% when that folder is not writable).
"""
import configparser
import ctypes
import logging
import os
import sys
import threading
import time
import traceback
from logging.handlers import RotatingFileHandler

import cv2
import numpy as np
from PIL import ImageGrab
from pynput import keyboard, mouse

try:
    import pystray
    from pystray import Menu, MenuItem
except ImportError:            # no tray library: run as a plain console program
    pystray = None

try:
    import winreg
except ImportError:            # not on Windows (only matters for testing)
    winreg = None

from tapicon import make_icon_image

APP_NAME = "Tap to skip"
WM_KEYDOWN = 0x0100
VK_MEDIA_NEXT_TRACK = 0xB0     # Windows virtual-key code for "Next track"
# What the buds send: volume, next, previous, stop, play/pause. Pressing
# these does not mean someone is at the computer, so they do not reset
# the idle timer that automatic mode uses.
MEDIA_KEYS = {0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3}

# --- Settings you may want to tune -------------------------------------
MATCH_THRESHOLD = 0.70   # 0..1, lower = more tolerant but more false matches
SEARCH_SECONDS = 12      # how long to keep looking after a double tap
SEARCH_INTERVAL = 0.3    # seconds between screenshots while searching
# Part of the screen to search, as fractions (left, top, right, bottom).
# (0.4, 0.4, 1.0, 1.0) is the lower-right area; (0, 0, 1, 1) is everything.
SEARCH_AREA = (0.4, 0.4, 1.0, 1.0)

AUTO_IDLE_SECONDS = 30   # automatic mode acts only after this long without input
AUTO_INTERVAL = 1.5      # seconds between screen checks in automatic mode
AUTO_AFTER_CLICK = 2.0   # pause after an automatic click (lets the page react)
AUTO_MAX_CLICKS = 3      # give up on a "button" that does not go away
AUTO_WINDOW_KEYWORDS = ("youtube",)   # active window title must contain one
# ------------------------------------------------------------------------

log = logging.getLogger("tap_to_skip")
mouse_ctl = mouse.Controller()
search_lock = threading.Lock()
template = None
listener = None
paused = False
auto_mode = True
running = False
_mutex = None
_data_dir = None


# ----------------------------------------------------------------- files
def base_dir():
    """Folder of the .exe when packed by PyInstaller, else the script's folder."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def data_dir():
    """A writable folder for the log and settings: next to the program, or
    the TapToSkip folder in %LOCALAPPDATA% when that is not possible."""
    global _data_dir
    if _data_dir is None:
        local = os.path.join(os.environ.get("LOCALAPPDATA", base_dir()), "TapToSkip")
        for folder in (base_dir(), local):
            try:
                os.makedirs(folder, exist_ok=True)
                with open(os.path.join(folder, "tap_to_skip.log"), "a", encoding="utf-8"):
                    pass
                _data_dir = folder
                break
            except OSError:
                continue
        else:
            _data_dir = base_dir()
    return _data_dir


def setup_logging():
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(message)s", "%Y-%m-%d %H:%M:%S")
    try:
        handler = RotatingFileHandler(
            os.path.join(data_dir(), "tap_to_skip.log"),
            maxBytes=200_000, backupCount=1, encoding="utf-8")
        handler.setFormatter(fmt)
        log.addHandler(handler)
    except OSError:
        pass
    if sys.stdout is not None:     # a console exists (e.g. running as a script)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(fmt)
        log.addHandler(handler)


SETTINGS_FILE = "tap_to_skip.ini"


def load_settings():
    global auto_mode
    cfg = configparser.ConfigParser()
    try:
        cfg.read(os.path.join(data_dir(), SETTINGS_FILE), encoding="utf-8")
        auto_mode = cfg.getboolean("settings", "auto_mode", fallback=True)
    except Exception:
        log.exception("could not read %s", SETTINGS_FILE)


def save_settings():
    cfg = configparser.ConfigParser()
    cfg["settings"] = {"auto_mode": "yes" if auto_mode else "no"}
    try:
        with open(os.path.join(data_dir(), SETTINGS_FILE), "w", encoding="utf-8") as f:
            cfg.write(f)
    except OSError:
        log.exception("could not save %s", SETTINGS_FILE)


# --------------------------------------------------------------- windows
def message_box(text, error=False):
    """Show a Windows message box. Works without a console window."""
    log.info("message: %s", text.replace("\n", " | "))
    flags = (0x10 if error else 0x40) | 0x40000   # MB_ICONERROR / MB_ICONINFORMATION, MB_TOPMOST
    try:
        ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, flags)
    except Exception:
        pass


def make_dpi_aware():
    """Make screenshots and mouse coordinates use real pixels, so that a
    screenshot taken with Win+Shift+S matches what we capture here."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def already_running():
    """True if another copy of the program is running (checked with a named mutex)."""
    global _mutex
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _mutex = kernel32.CreateMutexW(None, False, "TapToSkip-single-instance")
        return ctypes.get_last_error() == 183        # ERROR_ALREADY_EXISTS
    except Exception:
        return False


def foreground_title():
    """Title of the active window, or "" when it cannot be read."""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except Exception:
        return ""


def window_matches(title):
    title = title.lower()
    return any(keyword in title for keyword in AUTO_WINDOW_KEYWORDS)


# ------------------------------------------------------------- idle time
MASK = 0xFFFFFFFF


def elapsed(start, end):
    """Milliseconds from tick start to tick end (32-bit, wrap-safe)."""
    return (end - start) & MASK


def tick():
    return ctypes.windll.kernel32.GetTickCount() & MASK


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def last_input_tick():
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return info.dwTime
    return None


class IdleTracker:
    """Seconds since the user last touched the mouse or keyboard. Input that
    this program causes itself (its clicks) and media keys are not counted:
    call mark_own_input() just before such input happens."""

    def __init__(self):
        self.own_at = None     # tick when we last caused input
        self.before = None     # the real last-input tick just before that

    def _real_last(self):
        last = last_input_tick()
        if last is None:
            return None
        if self.own_at is not None and \
                elapsed((self.own_at - 200) & MASK, last) <= 1200:
            return self.before    # the latest input was ours
        return last

    def seconds(self):
        try:
            last = self._real_last()
            return elapsed(last, tick()) / 1000.0 if last is not None else 0.0
        except Exception:
            return 0.0

    def mark_own_input(self):
        try:
            self.before = self._real_last()
            self.own_at = tick()
        except Exception:
            pass


idle = IdleTracker()


# ----------------------------------------------------------- autostart
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "TapToSkip"


def start_command():
    """The command Windows runs at sign-in to start this program."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    python = pythonw if os.path.exists(pythonw) else sys.executable
    return f'"{python}" "{os.path.abspath(__file__)}"'


def autostart_enabled():
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE)
        return value == start_command()
    except OSError:
        return False


def set_autostart(enabled):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                        winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, start_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass


# ----------------------------------------------------- screen matching
def load_template(path):
    """Read skip.png as grayscale. Works with non-ASCII folder names too."""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
    except Exception:
        return None


def reload_template():
    global template
    path = os.path.join(base_dir(), "skip.png")
    template = load_template(path) if os.path.exists(path) else None
    if template is None:
        log.info("skip.png not found or unreadable: cursor mode")
    else:
        log.info("skip.png loaded (%dx%d px)", template.shape[1], template.shape[0])


def grab_search_area():
    """Screenshot the search area. Returns (grayscale image, x offset, y offset)."""
    screen = ImageGrab.grab()
    w, h = screen.size
    l, t, r, b = SEARCH_AREA
    box = (int(w * l), int(h * t), int(w * r), int(h * b))
    gray = cv2.cvtColor(np.array(screen.crop(box)), cv2.COLOR_RGB2GRAY)
    return gray, box[0], box[1]


def match(gray, tmpl, x_offset=0, y_offset=0):
    """Find tmpl in gray. Returns ((centre x, centre y), score) or (None, 0)."""
    th, tw = tmpl.shape
    if gray.shape[0] < th or gray.shape[1] < tw:
        return None, 0.0
    result = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(result)
    centre = (x_offset + loc[0] + tw // 2, y_offset + loc[1] + th // 2)
    return centre, float(score)


def find_on_screen(tmpl):
    gray, ox, oy = grab_search_area()
    return match(gray, tmpl, ox, oy)


def click_at(x, y):
    idle.mark_own_input()
    mouse_ctl.position = (x, y)
    time.sleep(0.05)
    mouse_ctl.click(mouse.Button.left)


def status_text():
    if template is None:
        return "Double tap: click at the cursor (no skip.png)"
    return "Double tap: find and click the Skip button"


def auto_status_text():
    if template is None:
        return "Automatic mode: needs skip.png"
    if not auto_mode:
        return "Automatic mode: off"
    return f"Automatic mode: on after {AUTO_IDLE_SECONDS:g} s idle in a YouTube window"


# --------------------------------------------------------- the double tap
def on_double_tap():
    if template is None:
        idle.mark_own_input()
        mouse_ctl.click(mouse.Button.left)
        log.info("double tap: clicked at the cursor position")
        return
    if not search_lock.acquire(blocking=False):
        log.info("double tap: already searching, ignored")
        return
    try:
        log.info("double tap: looking for the Skip button...")
        deadline = time.time() + SEARCH_SECONDS
        while time.time() < deadline:
            pos, score = find_on_screen(template)
            if pos and score >= MATCH_THRESHOLD:
                click_at(*pos)
                log.info("  found (score %.2f) at %s, clicked", score, pos)
                return
            time.sleep(SEARCH_INTERVAL)
        log.info("  no Skip button appeared, nothing clicked")
    finally:
        search_lock.release()


def win32_event_filter(msg, data):
    if data.vkCode in MEDIA_KEYS and msg == WM_KEYDOWN:
        idle.mark_own_input()              # a tap on the buds is not "activity"
    if data.vkCode != VK_MEDIA_NEXT_TRACK or paused:
        return True                        # not our key, or paused: let it through
    if msg == WM_KEYDOWN:
        try:
            # The search can take seconds, so never do it inside the hook.
            threading.Thread(target=on_double_tap, daemon=True).start()
        except Exception:
            log.exception("could not start the search")
    # Block the original "Next track" so YouTube doesn't jump to the next
    # video. suppress_event() must be the last call here.
    listener.suppress_event()
    return True


# -------------------------------------------------------- automatic mode
def auto_loop():
    """Runs in its own thread: look for the Skip button on a timer and click
    it, but only when nobody is using the computer and YouTube is the
    active window."""
    stuck_pos, stuck_count = None, 0
    while running:
        time.sleep(AUTO_INTERVAL)
        if paused or not auto_mode or template is None:
            continue
        if not window_matches(foreground_title()):
            continue
        idle_s = idle.seconds()
        if idle_s < AUTO_IDLE_SECONDS:
            continue
        if not search_lock.acquire(blocking=False):
            continue                       # a double-tap search is running
        try:
            pos, score = find_on_screen(template)
        finally:
            search_lock.release()
        if not pos or score < MATCH_THRESHOLD:
            stuck_pos, stuck_count = None, 0
            continue
        if stuck_pos and abs(pos[0] - stuck_pos[0]) <= 5 and abs(pos[1] - stuck_pos[1]) <= 5:
            stuck_count += 1
        else:
            stuck_pos, stuck_count = pos, 1
        if stuck_count > AUTO_MAX_CLICKS:
            if stuck_count == AUTO_MAX_CLICKS + 1:
                log.info("auto: the button at %s does not go away after %d clicks, "
                         "leaving it alone", pos, AUTO_MAX_CLICKS)
            continue
        click_at(*pos)
        log.info("auto: found (score %.2f) at %s, clicked (idle %.0f s)", score, pos, idle_s)
        time.sleep(AUTO_AFTER_CLICK)


# ------------------------------------------------------------------ test
def run_test(delay=5):
    if template is None:
        message_box("skip.png was not found next to the program, so there is "
                    "nothing to test.\n\nMode: click at the cursor position.")
        return
    time.sleep(delay)
    title = foreground_title()
    idle_s = idle.seconds()
    pos, score = find_on_screen(template)
    verdict = "FOUND" if score >= MATCH_THRESHOLD else "NOT FOUND"
    message_box(f"skip.png: {template.shape[1]}x{template.shape[0]} px\n"
                f"Best match: score {score:.2f} at {pos}\n"
                f"Threshold: {MATCH_THRESHOLD}\n"
                f"Result: {verdict}\n\n"
                f"Active window: {title[:70]}\n"
                f"Counts as YouTube: {'yes' if window_matches(title) else 'no'}\n"
                f"Idle: {idle_s:.0f} s (automatic mode needs {AUTO_IDLE_SECONDS:g} s)")


# ------------------------------------------------------------------ tray
def on_toggle_pause(icon, item):
    global paused
    paused = not paused
    icon.icon = make_icon_image(64, paused=paused)
    icon.update_menu()
    log.info("paused" if paused else "resumed")


def on_toggle_auto(icon, item):
    global auto_mode
    auto_mode = not auto_mode
    save_settings()
    icon.update_menu()
    log.info("automatic mode: %s", "on" if auto_mode else "off")


def on_toggle_autostart(icon, item):
    try:
        set_autostart(not autostart_enabled())
        log.info("start with Windows: %s", "on" if autostart_enabled() else "off")
    except Exception as e:
        message_box(f"Could not change the startup setting:\n{e}", error=True)
    icon.update_menu()


def on_test(icon, item):
    threading.Thread(target=run_test, daemon=True).start()


def on_reload(icon, item):
    reload_template()
    icon.update_menu()


def on_quit(icon, item):
    icon.stop()


def build_menu():
    return Menu(
        MenuItem(lambda item: status_text(), None, enabled=False),
        MenuItem(lambda item: auto_status_text(), None, enabled=False),
        Menu.SEPARATOR,
        MenuItem("Paused", on_toggle_pause, checked=lambda item: paused),
        MenuItem("Automatic mode", on_toggle_auto, checked=lambda item: auto_mode),
        MenuItem("Start with Windows", on_toggle_autostart,
                 checked=lambda item: autostart_enabled()),
        Menu.SEPARATOR,
        MenuItem("Test skip.png (in 5 s)", on_test),
        MenuItem("Reload skip.png", on_reload),
        Menu.SEPARATOR,
        MenuItem("Quit", on_quit),
    )


# ------------------------------------------------------------------ main
def main():
    global listener, running
    setup_logging()
    load_settings()
    make_dpi_aware()
    reload_template()

    if "--test" in sys.argv:
        run_test()
        return
    if already_running():
        message_box("Tap to skip is already running.\n\nLook for its icon in "
                    "the system tray (click the ^ arrow if it is hidden).")
        return

    listener = keyboard.Listener(win32_event_filter=win32_event_filter)
    listener.start()
    running = True
    threading.Thread(target=auto_loop, daemon=True, name="auto").start()
    log.info("started - %s; %s", status_text(), auto_status_text())

    if pystray is None:
        log.info("pystray is not installed: no tray icon, press Ctrl+C to stop")
        try:
            while listener.is_alive():
                listener.join(0.5)
        except KeyboardInterrupt:
            pass
    else:
        icon = pystray.Icon("tap_to_skip", make_icon_image(64), APP_NAME,
                            menu=build_menu())
        icon.run()                         # blocks until Quit
    running = False
    listener.stop()
    log.info("stopped")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("crashed")
        message_box("Tap to skip stopped with an error:\n\n"
                    + traceback.format_exc(), error=True)
