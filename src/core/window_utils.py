import ctypes
import os

import win32con
import win32gui
import win32process

# Constant cho DwmGetWindowAttribute
DWMWA_CLOAKED = 14


def is_window_cloaked(hwnd: int) -> bool:
    """
    Kiểm tra cửa sổ có đang bị 'cloaked' không.
    Cloaked = ẩn bởi hệ thống (UWP apps chạy ngầm, virtual desktop khác, v.v.)
    IsWindowVisible() KHÔNG phát hiện được trường hợp này.
    """
    cloaked_val = ctypes.c_int(0)
    result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked_val), ctypes.sizeof(cloaked_val)
    )
    return result == 0 and cloaked_val.value != 0


def get_all_visible_windows() -> list[tuple[str, int]]:
    """
    Trả về danh sách các cửa sổ đang hiển thị trên taskbar.
    Mỗi phần tử là (title, hwnd).
    Đã lọc: cửa sổ của chính app, cửa sổ ẩn, thu nhỏ, cloaked, toolwindow, quá nhỏ.
    """
    windows_list: list[tuple[str, int]] = []
    current_pid = os.getpid()

    def enum_callback(hwnd, _):
        # Bỏ qua cửa sổ của chính ứng dụng này
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid == current_pid:
            return True

        if not win32gui.IsWindowVisible(hwnd):
            return True

        title = win32gui.GetWindowText(hwnd)
        if not title.strip():
            return True

        # Loại bỏ cửa sổ đang thu nhỏ
        if win32gui.IsIconic(hwnd):
            return True

        # Loại bỏ cửa sổ bị "cloaked" (UWP apps trên virtual desktop khác, v.v.)
        if is_window_cloaked(hwnd):
            return True

        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        owner = win32gui.GetWindow(hwnd, win32con.GW_OWNER)

        is_tool_window = ex_style & win32con.WS_EX_TOOLWINDOW
        is_app_window = ex_style & win32con.WS_EX_APPWINDOW

        # Điều kiện taskbar: không phải ToolWindow và không có owner,
        # HOẶC có AppWindow style (override cả 2 điều kiện trên)
        if not ((not is_tool_window and owner == 0) or is_app_window):
            return True

        # Kích thước hợp lý
        left, top, right, bot = win32gui.GetWindowRect(hwnd)
        if (right - left) <= 100 or (bot - top) <= 100:
            return True

        windows_list.append((title, hwnd))
        return True

    win32gui.EnumWindows(enum_callback, None)
    return sorted(windows_list, key=lambda x: x[0].lower())
