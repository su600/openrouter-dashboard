"""Launch the dashboard and capture island + expanded screenshots."""
import subprocess, time, sys, os
import pyautogui
from PIL import ImageGrab
import ctypes

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SS_DIR = os.path.join(SCRIPT_DIR, "screenshots")
os.makedirs(SS_DIR, exist_ok=True)

# Launch the dashboard in a separate process
proc = subprocess.Popen([sys.executable, os.path.join(SCRIPT_DIR, "main.py")])

# Give it time to start and render
time.sleep(4)

# ── Find the window ──────────────────────────────────────────────────────────
import ctypes
from ctypes import wintypes

EnumWindows = ctypes.windll.user32.EnumWindows
GetWindowText = ctypes.windll.user32.GetWindowTextW
GetWindowRect = ctypes.windll.user32.GetWindowRect
IsWindowVisible = ctypes.windll.user32.IsWindowVisible
GetWindowLong = ctypes.windll.user32.GetWindowLongW

def find_dashboard():
    results = []
    def cb(hwnd, _):
        if IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            GetWindowText(hwnd, buf, 256)
            title = buf.value
            # overrideredirect windows have no title; look for small windows near top
            rect = wintypes.RECT()
            GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if 20 < w < 600 and 20 < h < 300:
                results.append((hwnd, title, rect.left, rect.top, w, h))
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    EnumWindows(WNDENUMPROC(cb), 0)
    return results

wins = find_dashboard()
print("Candidate windows:", wins)

# Wait a bit more if nothing found
if not wins:
    time.sleep(3)
    wins = find_dashboard()

print("Windows found:", wins)

# ── Screenshot helper ────────────────────────────────────────────────────────
def screenshot_window(rect, path, pad=8):
    """Capture a padded region around the window."""
    x, y, w, h = rect
    region = (
        max(0, x - pad),
        max(0, y - pad),
        x + w + pad,
        y + h + pad,
    )
    img = ImageGrab.grab(bbox=region, all_screens=True)
    img.save(path)
    print(f"Saved: {path}")

if wins:
    hwnd, title, x, y, w, h = wins[0]

    # Determine current state from window size
    # island ~ 270x36, expanded ~ 370x185
    is_island = (h < 60)
    print(f"Window: {w}x{h} at ({x},{y}) — {'island' if is_island else 'expanded'}")

    if is_island:
        # Screenshot island state first
        screenshot_window((x, y, w, h), os.path.join(SS_DIR, "island.png"))
        # Click center to expand
        cx, cy = x + w // 2, y + h // 2
        pyautogui.click(cx, cy)
        time.sleep(1.5)
        # Re-query window size
        rect2 = wintypes.RECT()
        GetWindowRect(hwnd, ctypes.byref(rect2))
        x2, y2 = rect2.left, rect2.top
        w2, h2 = rect2.right - rect2.left, rect2.bottom - rect2.top
        screenshot_window((x2, y2, w2, h2), os.path.join(SS_DIR, "expanded.png"))
    else:
        # Expanded first — screenshot, then click to collapse
        screenshot_window((x, y, w, h), os.path.join(SS_DIR, "expanded.png"))
        cx, cy = x + w // 2, y + h // 2
        pyautogui.click(cx, cy)
        time.sleep(1.5)
        rect2 = wintypes.RECT()
        GetWindowRect(hwnd, ctypes.byref(rect2))
        x2, y2 = rect2.left, rect2.top
        w2, h2 = rect2.right - rect2.left, rect2.bottom - rect2.top
        screenshot_window((x2, y2, w2, h2), os.path.join(SS_DIR, "island.png"))
else:
    # Fallback: full screenshot
    print("WARNING: window not found, taking full screenshot")
    img = ImageGrab.grab(all_screens=True)
    img.save(os.path.join(SS_DIR, "fullscreen.png"))

# Terminate the app
proc.terminate()
print("Done.")
