import os
import sys
import tkinter as tk
from tkinter import ttk

from src.core.app_config import load_config
from src.core.global_hotkey import (
    HOTKEY_ID_DESKTOP_CAPTURE,
    HOTKEY_ID_OPEN_AUTO_TAB,
    HOTKEY_ID_OPEN_DESKTOP_TAB,
    HOTKEY_ID_REGION_CAPTURE,
    HOTKEY_ID_START_RECORD,
    GlobalHotkeyListener,
)
from src.core.tray_icon import TrayIcon
from src.pages.page_auto_cap_window import PageAuto
from src.pages.page_desktop import PageDesktop
from src.pages.page_record import PageRecord
from src.pages.page_region import PageRegion
from src.pages.page_settings import PageSettings


def _resource_path(relative_path: str) -> str:
    """Trả về đường dẫn tài nguyên, hoạt động cả khi chạy từ mã nguồn lẫn khi đóng gói PyInstaller."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def _set_app_user_model_id():
    """Tách icon taskbar khỏi python.exe khi chạy từ mã nguồn (không cần khi đã đóng gói .exe)."""
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MLG.AutoCapture")
    except Exception:
        pass


def build_app():
    if not getattr(sys, "frozen", False):
        _set_app_user_model_id()

    root = tk.Tk()
    root.title("Tự Động Chụp Màn Hình")
    root.geometry("580x560")
    root.minsize(520, 500)
    root.configure(bg="#f0f0f0")

    icon_path = _resource_path(os.path.join("assets", "icons", "icon_app.ico"))
    if os.path.exists(icon_path):
        root.iconbitmap(icon_path)

    # ---- Tiêu đề app ----
    header = tk.Frame(root, bg="#1565c0", height=40, takefocus=False)
    header.pack(fill="x")
    header.pack_propagate(False)

    tk.Label(
        header,
        text="Tự Động Chụp Màn Hình",
        font=("Segoe UI", 13, "bold"),
        fg="white",
        bg="#1565c0",
    ).pack(side="left", padx=15, pady=10)

    # ---- Taps ----
    style = ttk.Style()
    style.theme_use("clam")
    style.layout("TNotebook", [])
    style.configure("TNotebook", background="#f0f0f0", borderwidth=0, takefocus=False)

    style.configure(
        "TNotebook.Tab",
        font=("Segoe UI", 10, "bold"),
        background="#dce3f0",
        foreground="#333",
        borderwidth=0,
        takefocus=False,
    )

    style.map(
        "TNotebook.Tab",
        background=[("selected", "#1565c0")],
        foreground=[("selected", "white")],
    )

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=0, pady=0)

    # Tab 1: Chụp tự động
    tab_auto = PageAuto(notebook, bg="#f5f5f5")
    notebook.add(tab_auto, text="Chụp Cửa Sổ")

    # Tab 2: Chụp theo vùng
    tab_region = PageRegion(notebook, bg="#f5f5f5")
    notebook.add(tab_region, text="Chụp Theo Vùng")

    # Tab 3: Chụp toàn bộ desktop
    tab_desktop = PageDesktop(notebook, bg="#f5f5f5")
    notebook.add(tab_desktop, text="Chụp Desktop")

    # Tab 4: Ghi màn hình
    tab_record = PageRecord(notebook, bg="#f5f5f5")
    notebook.add(tab_record, text="Ghi Màn Hình")

    # ---- Khay hệ thống ----
    def show_window():
        root.deiconify()
        root.lift()
        root.focus_force()

    def quit_app():
        hotkey_listener.stop()
        tray.stop()
        root.destroy()

    tray = TrayIcon(
        icon_path,
        "Tự Động Chụp Màn Hình",
        on_open=lambda: root.after(0, show_window),
        on_quit=lambda: root.after(0, quit_app),
    )
    tray.start()

    def on_close_window():
        config_data = load_config()
        if config_data.get("minimize_to_tray", True):
            root.withdraw()
        else:
            quit_app()

    root.protocol("WM_DELETE_WINDOW", on_close_window)

    # ---- Phím tắt toàn hệ thống ----
    def handle_hotkey(hotkey_id):
        if hotkey_id == HOTKEY_ID_OPEN_AUTO_TAB:
            show_window()
            notebook.select(tab_auto)
        elif hotkey_id == HOTKEY_ID_REGION_CAPTURE:
            tab_region._start_region_select()
        elif hotkey_id == HOTKEY_ID_DESKTOP_CAPTURE:
            tab_desktop._capture_now()
        elif hotkey_id == HOTKEY_ID_OPEN_DESKTOP_TAB:
            show_window()
            notebook.select(tab_desktop)
        elif hotkey_id == HOTKEY_ID_START_RECORD:
            show_window()
            notebook.select(tab_record)
            tab_record._toggle_record()

    hotkey_listener = GlobalHotkeyListener(
        on_hotkey=lambda hotkey_id: root.after(0, handle_hotkey, hotkey_id)
    )
    hotkey_listener.start()

    # Tab n: Cài đặt
    tab_settings = PageSettings(
        notebook, bg="#f5f5f5", on_hotkeys_changed=hotkey_listener.reload
    )
    notebook.add(tab_settings, text="Cài Đặt")

    root.mainloop()


if __name__ == "__main__":
    build_app()
