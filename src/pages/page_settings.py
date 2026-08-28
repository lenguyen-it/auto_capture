import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from src.core import startup
from src.core.app_config import load_config, save_config
from src.core.global_hotkey import hotkey_label
from src.pages.components.hotkey_capture import HotkeyCapture

_HOTKEY_FIELDS = [
    ("hotkey_open_auto_tab", "Mở cửa sổ & chuyển sang tab Chụp Tự Động"),
    ("hotkey_region_capture", "Mở ngay công cụ kéo chọn vùng để chụp"),
    ("hotkey_desktop_capture", "Chụp ngay toàn bộ desktop"),
    ("hotkey_open_desktop_tab", "Mở cửa sổ & chuyển sang tab Chụp Desktop"),
]


class PageSettings(tk.Frame):
    """Frame cho tab Cài đặt."""

    def __init__(self, parent, on_hotkeys_changed=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(bg="#f5f5f5")

        self.config_data = load_config()
        self.on_hotkeys_changed = on_hotkeys_changed
        self._hotkey_labels: dict[str, tk.Label] = {}
        self._hotkey_buttons: dict[str, tk.Button] = {}
        self._active_capture: HotkeyCapture | None = None
        self._active_capture_key: str | None = None
        self._build_ui()

    def _build_ui(self):
        section_general = tk.LabelFrame(
            self,
            text="Chung",
            font=("Segoe UI", 10, "bold"),
            bg="#f5f5f5",
            fg="#1565c0",
            bd=1,
            relief="groove",
        )
        section_general.pack(fill="x", padx=15, pady=(10, 4))

        self.var_start_with_windows = tk.BooleanVar(
            value=self.config_data.get("start_with_windows", False)
        )
        tk.Checkbutton(
            section_general,
            text="Tự khởi động cùng Windows",
            variable=self.var_start_with_windows,
            font=("Segoe UI", 10),
            bg="#f5f5f5",
            command=self._on_toggle_start_with_windows,
        ).pack(anchor="w", padx=10, pady=(8, 2))

        self.var_minimize_to_tray = tk.BooleanVar(
            value=self.config_data.get("minimize_to_tray", True)
        )
        tk.Checkbutton(
            section_general,
            text="Thu nhỏ xuống khay hệ thống khi đóng cửa sổ",
            variable=self.var_minimize_to_tray,
            font=("Segoe UI", 10),
            bg="#f5f5f5",
            command=self._on_toggle_minimize_to_tray,
        ).pack(anchor="w", padx=10, pady=(2, 8))

        section_folder = tk.LabelFrame(
            self,
            text="Thư mục lưu ảnh mặc định",
            font=("Segoe UI", 10, "bold"),
            bg="#f5f5f5",
            fg="#1565c0",
            bd=1,
            relief="groove",
        )
        section_folder.pack(fill="x", padx=15, pady=4)

        frame_folder = tk.Frame(section_folder, bg="#f5f5f5")
        frame_folder.pack(fill="x", padx=10, pady=8)

        self.entry_folder = tk.Entry(frame_folder, font=("Segoe UI", 10))
        self.entry_folder.insert(0, self.config_data.get("default_save_folder", ""))
        self.entry_folder.config(state="readonly")
        self.entry_folder.pack(side="left", fill="x", expand=True)

        tk.Button(
            frame_folder,
            text="Chọn",
            command=self._select_folder,
            font=("Segoe UI", 9),
            relief="flat",
            bg="#e0e0e0",
            cursor="hand2",
        ).pack(side="right", padx=5)

        section_image = tk.LabelFrame(
            self,
            text="Định dạng ảnh",
            font=("Segoe UI", 10, "bold"),
            bg="#f5f5f5",
            fg="#1565c0",
            bd=1,
            relief="groove",
        )
        section_image.pack(fill="x", padx=15, pady=4)

        frame_format = tk.Frame(section_image, bg="#f5f5f5")
        frame_format.pack(fill="x", padx=10, pady=(8, 4))

        tk.Label(
            frame_format,
            text="Loại file:",
            font=("Segoe UI", 10),
            bg="#f5f5f5",
        ).pack(side="left")

        self.var_image_format = tk.StringVar(
            value=self.config_data.get("image_format", "PNG")
        )
        cb_format = ttk.Combobox(
            frame_format,
            textvariable=self.var_image_format,
            values=["PNG", "JPEG"],
            state="readonly",
            width=8,
            font=("Segoe UI", 10),
        )
        cb_format.pack(side="left", padx=5)
        cb_format.bind("<<ComboboxSelected>>", self._on_change_image_format)

        # --- PNG: mức nén (không đổi chất lượng, chỉ đổi tốc độ/dung lượng) ---
        self.frame_png = tk.Frame(section_image, bg="#f5f5f5")
        row_png_label = tk.Frame(self.frame_png, bg="#f5f5f5")
        row_png_label.pack(fill="x", padx=10)
        tk.Label(
            row_png_label,
            text="Chất lượng PNG:",
            font=("Segoe UI", 9),
            bg="#f5f5f5",
            fg="#555",
        ).pack(side="left")

        self.var_png_level = tk.IntVar(
            value=self.config_data.get("png_compress_level", 6)
        )
        self.lbl_png_level_value = tk.Label(
            row_png_label,
            text=str(self.var_png_level.get()),
            font=("Segoe UI", 12, "bold"),
            bg="#f5f5f5",
            fg="#1565c0",
        )
        self.lbl_png_level_value.pack(side="right")
        scale_png = ttk.Scale(
            self.frame_png,
            from_=0,
            to=9,
            orient="horizontal",
            variable=self.var_png_level,
            command=lambda _v: self.lbl_png_level_value.config(
                text=str(self.var_png_level.get())
            ),
        )
        scale_png.pack(fill="x", padx=10)
        scale_png.bind("<ButtonRelease-1>", self._on_change_png_level)

        tk.Label(
            self.frame_png,
            text="0 = lưu nhanh, file to   |   9 = lưu chậm, file nhỏ",
            font=("Segoe UI", 8, "italic"),
            bg="#f5f5f5",
            fg="#999",
        ).pack(anchor="w", padx=10, pady=(0, 8))

        # --- JPEG: chất lượng ---
        self.frame_jpeg = tk.Frame(section_image, bg="#f5f5f5")
        row_jpeg_label = tk.Frame(self.frame_jpeg, bg="#f5f5f5")
        row_jpeg_label.pack(fill="x", padx=10)
        tk.Label(
            row_jpeg_label,
            text="Chất lượng JPEG:",
            font=("Segoe UI", 9),
            bg="#f5f5f5",
            fg="#555",
        ).pack(side="left")

        self.var_jpeg_quality = tk.IntVar(
            value=self.config_data.get("jpeg_quality", 90)
        )
        self.lbl_jpeg_quality_value = tk.Label(
            row_jpeg_label,
            text=str(self.var_jpeg_quality.get()),
            font=("Segoe UI", 9, "bold"),
            bg="#f5f5f5",
            fg="#1565c0",
        )
        self.lbl_jpeg_quality_value.pack(side="right")
        scale_jpeg = ttk.Scale(
            self.frame_jpeg,
            from_=1,
            to=100,
            orient="horizontal",
            variable=self.var_jpeg_quality,
            command=lambda _v: self.lbl_jpeg_quality_value.config(
                text=str(self.var_jpeg_quality.get())
            ),
        )
        scale_jpeg.pack(fill="x", padx=10)
        scale_jpeg.bind("<ButtonRelease-1>", self._on_change_jpeg_quality)

        tk.Label(
            self.frame_jpeg,
            text="Càng cao càng nét, file càng nặng",
            font=("Segoe UI", 8, "italic"),
            bg="#f5f5f5",
            fg="#999",
        ).pack(anchor="w", padx=10, pady=(0, 8))

        self._update_image_format_ui()

        section_hotkey = tk.LabelFrame(
            self,
            text="Phím tắt nhanh",
            font=("Segoe UI", 10, "bold"),
            bg="#f5f5f5",
            fg="#1565c0",
            bd=1,
            relief="groove",
        )
        section_hotkey.pack(fill="x", padx=15, pady=4)

        for config_key, description in _HOTKEY_FIELDS:
            row = tk.Frame(section_hotkey, bg="#f5f5f5")
            row.pack(fill="x", padx=10, pady=4)

            tk.Label(
                row,
                text=description,
                font=("Segoe UI", 9),
                bg="#f5f5f5",
                fg="#555",
                anchor="w",
                wraplength=280,
                justify="left",
            ).pack(side="left", fill="x", expand=True)

            lbl_current = tk.Label(
                row,
                text=self._current_hotkey_label(config_key),
                font=("Segoe UI", 9, "bold"),
                bg="#e8e8e8",
                fg="#1565c0",
                width=14,
                relief="groove",
            )
            lbl_current.pack(side="left", padx=(5, 5))
            self._hotkey_labels[config_key] = lbl_current

            btn_record = tk.Button(
                row,
                text="Ghi",
                font=("Segoe UI", 9),
                relief="flat",
                bg="#e0e0e0",
                cursor="hand2",
                command=lambda k=config_key: self._start_capture(k),
            )
            btn_record.pack(side="right")
            self._hotkey_buttons[config_key] = btn_record

        tk.Label(
            section_hotkey,
            text='Bấm "Ghi" rồi nhấn tổ hợp phím muốn dùng (Esc để hủy).',
            font=("Segoe UI", 8, "italic"),
            bg="#f5f5f5",
            fg="#999",
            anchor="w",
        ).pack(fill="x", padx=10, pady=(0, 8))

    def _on_toggle_start_with_windows(self):
        enabled = self.var_start_with_windows.get()
        try:
            startup.set_enabled(enabled)
        except OSError as e:
            messagebox.showerror(
                "Lỗi", f"Không thể cập nhật khởi động cùng Windows: {e}"
            )
            self.var_start_with_windows.set(not enabled)
            return
        self.config_data["start_with_windows"] = enabled
        save_config(self.config_data)

    def _on_toggle_minimize_to_tray(self):
        self.config_data["minimize_to_tray"] = self.var_minimize_to_tray.get()
        save_config(self.config_data)

    def _update_image_format_ui(self):
        self.frame_png.pack_forget()
        self.frame_jpeg.pack_forget()
        if self.var_image_format.get() == "JPEG":
            self.frame_jpeg.pack(fill="x")
        else:
            self.frame_png.pack(fill="x")

    def _on_change_image_format(self, _event=None):
        self.config_data["image_format"] = self.var_image_format.get()
        save_config(self.config_data)
        self._update_image_format_ui()

    def _on_change_png_level(self, _value=None):
        self.config_data["png_compress_level"] = self.var_png_level.get()
        save_config(self.config_data)

    def _on_change_jpeg_quality(self, _value=None):
        self.config_data["jpeg_quality"] = self.var_jpeg_quality.get()
        save_config(self.config_data)

    def _current_hotkey_label(self, config_key: str) -> str:
        entry = self.config_data.get(config_key, {})
        mods, vk = entry.get("mods", 0), entry.get("vk", 0)
        return hotkey_label(mods, vk) if vk else "(chưa đặt)"

    def _start_capture(self, config_key: str):
        # Nếu đang ghi phím khác thì hủy trước
        if self._active_capture is not None and self._active_capture_key is not None:
            self._active_capture.cancel()
            self._reset_button_label(self._active_capture_key)

        self._active_capture_key = config_key
        lbl = self._hotkey_labels[config_key]
        lbl.config(text="Nhấn phím...", fg="#e65100")
        self._hotkey_buttons[config_key].config(state="disabled")

        capture = HotkeyCapture(
            self,
            on_captured=lambda result, k=config_key: self._on_hotkey_captured(
                k, result
            ),
        )
        self._active_capture = capture
        capture.start()

    def _reset_button_label(self, config_key: str):
        self._hotkey_labels[config_key].config(
            text=self._current_hotkey_label(config_key), fg="#1565c0"
        )
        self._hotkey_buttons[config_key].config(state="normal")

    def _on_hotkey_captured(self, config_key: str, result):
        self._active_capture = None
        self._active_capture_key = None
        self._hotkey_buttons[config_key].config(state="normal")

        if result is None:
            self._reset_button_label(config_key)
            return

        mods, vk = result
        self.config_data[config_key] = {"mods": mods, "vk": vk}
        save_config(self.config_data)
        self._hotkey_labels[config_key].config(
            text=hotkey_label(mods, vk), fg="#1565c0"
        )

        if self.on_hotkeys_changed:
            self.on_hotkeys_changed()

    def _select_folder(self):
        folder = filedialog.askdirectory(title="Chọn thư mục lưu ảnh mặc định")
        if folder:
            self.config_data["default_save_folder"] = folder
            save_config(self.config_data)
            self.entry_folder.config(state="normal")
            self.entry_folder.delete(0, tk.END)
            self.entry_folder.insert(0, folder)
            self.entry_folder.config(state="readonly")
