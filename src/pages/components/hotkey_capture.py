import tkinter as tk

from src.core.global_hotkey import MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN

_MODIFIER_KEYSYMS = {
    "Control_L", "Control_R",
    "Alt_L", "Alt_R",
    "Shift_L", "Shift_R",
    "Super_L", "Super_R",
    "Win_L", "Win_R",
}

# keysym -> mã phím ảo Win32 (VK_*) cho các phím thường dùng làm hotkey
_KEYSYM_TO_VK = {}
for _c in "0123456789":
    _KEYSYM_TO_VK[_c] = ord(_c)
for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    _KEYSYM_TO_VK[_c] = ord(_c)
    _KEYSYM_TO_VK[_c.lower()] = ord(_c)
for _i in range(1, 13):
    _KEYSYM_TO_VK[f"F{_i}"] = 0x70 + (_i - 1)


def keysym_to_vk(keysym: str) -> int | None:
    return _KEYSYM_TO_VK.get(keysym)


class HotkeyCapture:
    """Bắt tổ hợp phím do người dùng nhấn trên một Entry, trả về (mods, vk) kiểu Win32.

    Dùng cho ô "Ghi phím tắt": khi active, phím Ctrl/Alt/Shift/Win được cộng dồn
    làm modifier, phím tiếp theo không phải modifier được coi là phím chính và
    kết thúc việc ghi.
    """

    def __init__(self, widget: tk.Widget, on_captured):
        self.widget = widget
        self.on_captured = on_captured
        self._mods = 0
        self._active = False

    def start(self):
        self._mods = 0
        self._active = True
        self.widget.bind("<KeyPress>", self._on_key_press)
        self.widget.focus_set()

    def cancel(self):
        self._active = False
        self.widget.unbind("<KeyPress>")

    def _on_key_press(self, event):
        if not self._active:
            return "break"

        keysym = event.keysym

        if keysym in _MODIFIER_KEYSYMS:
            if keysym.startswith("Control"):
                self._mods |= MOD_CONTROL
            elif keysym.startswith("Alt"):
                self._mods |= MOD_ALT
            elif keysym.startswith("Shift"):
                self._mods |= MOD_SHIFT
            else:
                self._mods |= MOD_WIN
            return "break"

        if keysym == "Escape":
            self.cancel()
            self.on_captured(None)
            return "break"

        vk = keysym_to_vk(keysym)
        if vk is None:
            # Phím không hỗ trợ làm hotkey (vd. dấu cách, phím mũi tên...)
            return "break"

        mods, self._mods = self._mods, 0
        self.cancel()
        self.on_captured((mods, vk))
        return "break"
