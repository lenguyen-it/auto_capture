import json
import os

_CONFIG_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "AutoCapture"
)
_CONFIG_PATH = os.path.join(_CONFIG_DIR, "config.json")

DEFAULTS = {
    "start_with_windows": False,
    "minimize_to_tray": True,
    "default_save_folder": os.path.abspath("screenshots"),
    # mods = tổ hợp MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_WIN (xem src/core/global_hotkey.py)
    "hotkey_open_auto_tab": {"mods": 3, "vk": ord("1")},  # Ctrl+Alt+1
    "hotkey_region_capture": {"mods": 3, "vk": ord("2")},  # Ctrl+Alt+2
    "hotkey_desktop_capture": {"mods": 3, "vk": ord("3")},  # Ctrl+Alt+3
    "hotkey_open_desktop_tab": {"mods": 3, "vk": ord("4")},  # Ctrl+Alt+4
    "image_format": "PNG",  # "PNG" hoặc "JPEG"
    "png_compress_level": 6,  # 0 (nhanh, file to) - 9 (chậm, file nhỏ) - không mất dữ liệu
    "jpeg_quality": 90,  # 1 (nhẹ, mất nhiều chi tiết) - 100 (nặng, gần như lossless)
}


def load_config() -> dict:
    if not os.path.exists(_CONFIG_PATH):
        return dict(DEFAULTS)
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULTS)
        merged.update(data)
        return merged
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULTS)


def save_config(config: dict) -> None:
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
