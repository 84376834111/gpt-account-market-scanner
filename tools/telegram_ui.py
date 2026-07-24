from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
import time
from pathlib import Path
from ctypes import wintypes


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
sys.stdout.reconfigure(encoding="utf-8")

kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE

try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    pass

SW_RESTORE = 9
SW_MAXIMIZE = 3
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_WHEEL = 0x0800
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

VK = {
    "ctrl": 0x11,
    "shift": 0x10,
    "alt": 0x12,
    "enter": 0x0D,
    "esc": 0x1B,
    "tab": 0x09,
    "a": 0x41,
    "c": 0x43,
    "f": 0x46,
    "v": 0x56,
}


def telegram_pids() -> set[int]:
    output = subprocess.check_output(
        ["powershell", "-NoProfile", "-Command", "(Get-Process Telegram).Id"],
        text=True,
        creationflags=0x08000000,
    )
    return {int(line.strip()) for line in output.splitlines() if line.strip().isdigit()}


def find_window() -> tuple[int, str, tuple[int, int, int, int]]:
    pids = telegram_pids()
    windows: list[tuple[int, str, tuple[int, int, int, int], bool]] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def callback(hwnd: int, _lparam: int) -> bool:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in pids:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        size = (rect.right - rect.left) * (rect.bottom - rect.top)
        if size > 10_000:
            windows.append(
                (
                    int(hwnd),
                    title.value,
                    (rect.left, rect.top, rect.right, rect.bottom),
                    bool(user32.IsWindowVisible(hwnd)),
                )
            )
        return True

    user32.EnumWindows(callback, 0)
    if not windows:
        raise RuntimeError("Telegram window not found")
    interactive = [
        item
        for item in windows
        if item[3] and item[1] and item[1] != "QTrayIconMessageWindow"
    ]
    if interactive:
        windows = interactive
    windows.sort(key=lambda item: ((item[2][2] - item[2][0]) * (item[2][3] - item[2][1]), item[3]), reverse=True)
    hwnd, title, rect, _visible = windows[0]
    return hwnd, title, rect


def activate() -> tuple[int, tuple[int, int, int, int]]:
    hwnd, _title, _rect = find_window()
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.35)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return hwnd, (rect.left, rect.top, rect.right, rect.bottom)


def maximize() -> None:
    hwnd, _title, _rect = find_window()
    user32.ShowWindow(hwnd, SW_MAXIMIZE)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)


def resize(width: int, height: int) -> None:
    hwnd, _title, _rect = find_window()
    if not user32.MoveWindow(hwnd, 0, 0, max(900, width), max(650, height), True):
        raise RuntimeError("Unable to resize Telegram window")
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)


def key(vk: int, down: bool) -> None:
    user32.keybd_event(vk, 0, 0 if down else KEYEVENTF_KEYUP, 0)


def hotkey(*names: str) -> None:
    keys = [VK[name.lower()] for name in names]
    for item in keys:
        key(item, True)
    for item in reversed(keys):
        key(item, False)
    time.sleep(0.12)


def set_clipboard(text: str) -> None:
    encoded = (text + "\0").encode("utf-16-le")
    if not user32.OpenClipboard(None):
        raise RuntimeError("Unable to open clipboard")
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
        pointer = kernel32.GlobalLock(handle)
        ctypes.memmove(pointer, encoded, len(encoded))
        kernel32.GlobalUnlock(handle)
        user32.SetClipboardData(CF_UNICODETEXT, handle)
    finally:
        user32.CloseClipboard()


def get_clipboard() -> str:
    if not user32.OpenClipboard(None):
        return ""
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        pointer = kernel32.GlobalLock(handle)
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def click(relative_x: int, relative_y: int) -> None:
    _hwnd, rect = activate()
    x = rect[0] + relative_x
    y = rect[1] + relative_y
    user32.SetCursorPos(x, y)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.25)


def scroll(relative_x: int, relative_y: int, delta: int) -> None:
    _hwnd, rect = activate()
    user32.SetCursorPos(rect[0] + relative_x, rect[1] + relative_y)
    user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, delta, 0)
    time.sleep(0.35)


def screenshot(path: Path) -> None:
    _hwnd, rect = activate()
    from PIL import ImageGrab

    path.parent.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab(bbox=rect, all_screens=True).save(path)


def search(query: str, search_x: int, search_y: int) -> None:
    click(search_x, search_y)
    hotkey("ctrl", "a")
    set_clipboard(query)
    hotkey("ctrl", "v")
    time.sleep(2.5)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("info")
    sub.add_parser("maximize")
    window = sub.add_parser("resize")
    window.add_argument("width", type=int)
    window.add_argument("height", type=int)
    shot = sub.add_parser("shot")
    shot.add_argument("path", type=Path)
    point = sub.add_parser("click")
    point.add_argument("x", type=int)
    point.add_argument("y", type=int)
    wheel = sub.add_parser("scroll")
    wheel.add_argument("x", type=int)
    wheel.add_argument("y", type=int)
    wheel.add_argument("delta", type=int)
    query = sub.add_parser("search")
    query.add_argument("text")
    query.add_argument("--x", type=int, default=230)
    query.add_argument("--y", type=int, default=51)
    keys = sub.add_parser("hotkey")
    keys.add_argument("keys", nargs="+")
    clip = sub.add_parser("clipboard")
    clip.add_argument("--set")

    args = parser.parse_args()
    if args.command == "info":
        hwnd, title, rect = find_window()
        print(json.dumps({"hwnd": hwnd, "title": title, "rect": rect}, ensure_ascii=False))
    elif args.command == "maximize":
        maximize()
    elif args.command == "resize":
        resize(args.width, args.height)
    elif args.command == "shot":
        screenshot(args.path.resolve())
        print(args.path.resolve())
    elif args.command == "click":
        click(args.x, args.y)
    elif args.command == "scroll":
        scroll(args.x, args.y, args.delta)
    elif args.command == "search":
        search(args.text, args.x, args.y)
    elif args.command == "hotkey":
        activate()
        hotkey(*args.keys)
    elif args.command == "clipboard":
        if args.set is not None:
            set_clipboard(args.set)
        else:
            print(get_clipboard())


if __name__ == "__main__":
    main()
