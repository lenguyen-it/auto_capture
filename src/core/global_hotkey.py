import ctypes
import ctypes.wintypes
import threading

from src.core.app_config import load_config

user32 = ctypes.windll.user32

WM_HOTKEY = 0x0312
WM_USER_REBIND = 0x0400 + 1

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

MOD_NAMES = [
    (MOD_CONTROL, "Ctrl"),
    (MOD_ALT, "Alt"),
    (MOD_SHIFT, "Shift"),
    (MOD_WIN, "Win"),
]

HOTKEY_ID_OPEN_AUTO_TAB = 1
HOTKEY_ID_REGION_CAPTURE = 2
HOTKEY_ID_DESKTOP_CAPTURE = 3
HOTKEY_ID_OPEN_DESKTOP_TAB = 4

_CONFIG_KEYS = {
    HOTKEY_ID_OPEN_AUTO_TAB: "hotkey_open_auto_tab",
    HOTKEY_ID_REGION_CAPTURE: "hotkey_region_capture",
    HOTKEY_ID_DESKTOP_CAPTURE: "hotkey_desktop_capture",
    HOTKEY_ID_OPEN_DESKTOP_TAB: "hotkey_open_desktop_tab",
}


def vk_to_label(vk: int) -> str:
    """Tên hiển thị của phím chính (vd. 49 -> '1', 112 -> 'F1')."""
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    return f"VK{vk:02X}"


def hotkey_label(mods: int, vk: int) -> str:
    parts = [name for flag, name in MOD_NAMES if mods & flag]
    parts.append(vk_to_label(vk))
    return "+".join(parts)


def _load_bindings() -> dict[int, tuple[int, int]]:
    config = load_config()
    bindings = {}
    for hotkey_id, config_key in _CONFIG_KEYS.items():
        entry = config.get(config_key, {})
        bindings[hotkey_id] = (entry.get("mods", 0), entry.get("vk", 0))
    return bindings


class GlobalHotkeyListener:
    """Lắng nghe phím tắt toàn hệ thống bằng RegisterHotKey, chạy trên thread riêng
    có message loop win32 (Tkinter mainloop không nhận được WM_HOTKEY).

    Tổ hợp phím được nạp từ config lúc khởi động; gọi reload() sau khi người
    dùng đổi phím tắt trong Cài Đặt để đăng ký lại ngay, không cần khởi động lại app.
    """

    def __init__(self, on_hotkey):
        self._on_hotkey = on_hotkey
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread_id: int | None = None
        self._registered: set[int] = set()

    def start(self):
        self._thread.start()

    def reload(self):
        """Yêu cầu thread lắng nghe đăng ký lại toàn bộ hotkey từ config hiện tại."""
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_USER_REBIND, 0, 0)

    def _register_all(self):
        for hotkey_id in self._registered:
            user32.UnregisterHotKey(None, hotkey_id)
        self._registered.clear()

        for hotkey_id, (mods, vk) in _load_bindings().items():
            if not vk:
                continue
            if user32.RegisterHotKey(None, hotkey_id, mods, vk):
                self._registered.add(hotkey_id)
            else:
                print(f"[Hotkey] Không đăng ký được hotkey id={hotkey_id}")

    def _run(self):
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        self._register_all()

        msg = ctypes.wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                if msg.message == WM_HOTKEY:
                    self._on_hotkey(msg.wParam)
                elif msg.message == WM_USER_REBIND:
                    self._register_all()
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            for hotkey_id in self._registered:
                user32.UnregisterHotKey(None, hotkey_id)

    def stop(self):
        if self._thread_id:
            WM_QUIT = 0x0012
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
