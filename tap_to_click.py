"""
tap_to_click  -  Pixel Buds A double tap -> mouse click (Windows)

Modes
-----
1. No skip.png next to the program:
   double tap  ->  left click at the current cursor position.

2. skip.png present (a tight crop of the Skip button's text and icon):
   double tap  ->  search the screen for skip.png for up to SEARCH_SECONDS
                   and click its centre when found. Nothing is clicked if
                   the button never appears.

Test mode:   tap_to_click.exe --test
   Waits 5 seconds (switch to the browser), takes one screenshot and reports
   how well skip.png matches and where. Run it while an ad with a visible
   Skip button is on screen, and once with no ad to check for false matches.

A single tap (Play/Pause) is never touched.
Stop with Ctrl+C in the console window, or close the window.
"""
import ctypes
import os
import sys
import threading
import time

import cv2
import numpy as np
from PIL import ImageGrab
from pynput import keyboard, mouse

VK_MEDIA_NEXT_TRACK = 0xB0  # Windows virtual-key code for "Next track"
WM_KEYDOWN = 0x0100

# --- Settings you may want to tune -------------------------------------
MATCH_THRESHOLD = 0.70   # 0..1, lower = more tolerant but more false matches
SEARCH_SECONDS = 12      # how long to keep looking after a double tap
SEARCH_INTERVAL = 0.3    # seconds between screenshots while searching
# Part of the screen to search, as fractions (left, top, right, bottom).
# (0.4, 0.4, 1.0, 1.0) is the lower-right area; (0, 0, 1, 1) is everything.
SEARCH_AREA = (0.4, 0.4, 1.0, 1.0)
# ------------------------------------------------------------------------

mouse_ctl = mouse.Controller()
search_lock = threading.Lock()
template = None


def base_dir():
    """Folder of the .exe when packed by PyInstaller, else the script's folder."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


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


def load_template(path):
    """Read skip.png as grayscale. Works with non-ASCII folder names too."""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
    except Exception:
        return None


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
    mouse_ctl.position = (x, y)
    time.sleep(0.05)
    mouse_ctl.click(mouse.Button.left)


def on_double_tap():
    if template is None:
        mouse_ctl.click(mouse.Button.left)
        print("Double tap: clicked at the cursor position.")
        return
    if not search_lock.acquire(blocking=False):
        print("Double tap: already searching, ignored.")
        return
    try:
        print("Double tap: looking for the Skip button...")
        deadline = time.time() + SEARCH_SECONDS
        while time.time() < deadline:
            pos, score = find_on_screen(template)
            if pos and score >= MATCH_THRESHOLD:
                click_at(*pos)
                print(f"  found (score {score:.2f}) at {pos}, clicked.")
                return
            time.sleep(SEARCH_INTERVAL)
        print("  no Skip button appeared, nothing clicked.")
    finally:
        search_lock.release()


def win32_event_filter(msg, data):
    if data.vkCode == VK_MEDIA_NEXT_TRACK:
        if msg == WM_KEYDOWN:
            # The search can take seconds, so never do it inside the hook.
            threading.Thread(target=on_double_tap, daemon=True).start()
        # Block the original "Next track" so YouTube doesn't jump to the
        # next video. (suppress_event() must be the last thing here.)
        listener.suppress_event()
    return True


listener = keyboard.Listener(win32_event_filter=win32_event_filter)


def run_test():
    if template is None:
        print("skip.png was not found next to the program.")
        return
    print(f"skip.png loaded: {template.shape[1]}x{template.shape[0]} pixels.")
    for i in range(5, 0, -1):
        print(f"Taking a screenshot in {i}... switch to the browser now.")
        time.sleep(1)
    pos, score = find_on_screen(template)
    verdict = "FOUND" if score >= MATCH_THRESHOLD else "NOT FOUND"
    print(f"Best match: score {score:.2f} at {pos} "
          f"(threshold {MATCH_THRESHOLD}) -> {verdict}")


def main():
    global template
    make_dpi_aware()
    path = os.path.join(base_dir(), "skip.png")
    if os.path.exists(path):
        template = load_template(path)
        if template is None:
            print("skip.png exists but could not be read; using cursor mode.")

    if "--test" in sys.argv:
        run_test()
        return

    if template is None:
        print("Mode: double tap = click at the cursor position "
              "(no skip.png found).")
    else:
        print("Mode: double tap = find and click the Skip button (skip.png).")
    print("Single tap is untouched. Press Ctrl+C to stop.")

    listener.start()
    try:
        while listener.is_alive():
            listener.join(0.5)
    except KeyboardInterrupt:
        listener.stop()
        print("Stopped.")


if __name__ == "__main__":
    main()
