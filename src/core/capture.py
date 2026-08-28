import ctypes
import os
from datetime import datetime

import win32con
import win32gui
import win32ui
from PIL import Image

from src.core.app_config import load_config

# ---------------------------------------------------------------------------
# Chụp cửa sổ theo HWND (PrintWindow)
# ---------------------------------------------------------------------------


def capture_window_by_hwnd(
    hwnd: int,
    title: str,
    base_folder: str,
    file_prefix: str = "cap",
) -> bool:
    """
    Chụp cửa sổ bằng PrintWindow API.
    Trả về True nếu thành công, False nếu thất bại.
    Ảnh được lưu vào: base_folder/YYYY-MM-DD/{file_prefix}_{timestamp}.png
    """
    if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
        print(f"Cửa sổ '{title}' đã bị đóng hoặc ẩn.")
        return False

    left, top, right, bot = win32gui.GetWindowRect(hwnd)
    w, h = right - left, bot - top

    if w <= 0 or h <= 0:
        print(f"Cửa sổ '{title}' bị chặn hoặc đang thu nhỏ.")
        return False

    try:
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()

        save_bmp = win32ui.CreateBitmap()
        save_bmp.CreateCompatibleBitmap(mfc_dc, w, h)
        save_dc.SelectObject(save_bmp)

        result = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 3)

        bmpinfo = save_bmp.GetInfo()
        bmpstr = save_bmp.GetBitmapBits(True)
        im = Image.frombuffer(
            "RGB",
            (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
            bmpstr,
            "raw",
            "BGRX",
            0,
            1,
        )

        win32gui.DeleteObject(save_bmp.GetHandle())
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)

        if result == 1:
            saved_path = _save_image(im, base_folder, file_prefix, title)
            return saved_path is not None

    except Exception as e:
        print(f"Lỗi khi chụp cửa sổ: {e}")

    return False


# ---------------------------------------------------------------------------
# Chụp vùng màn hình theo tọa độ (BitBlt từ desktop)
# ---------------------------------------------------------------------------


def grab_region(x1: int, y1: int, x2: int, y2: int) -> Image.Image | None:
    """
    Chụp vùng màn hình xác định bởi (x1, y1) -> (x2, y2) (tọa độ màn hình tuyệt đối).
    Trả về ảnh PIL (không lưu file), None nếu thất bại.
    """
    left, top = min(x1, x2), min(y1, y2)
    right, bot = max(x1, x2), max(y1, y2)
    w, h = right - left, bot - top

    if w <= 0 or h <= 0:
        return None

    try:
        # Lấy DC của toàn bộ màn hình (desktop)
        hdesktop = win32gui.GetDesktopWindow()
        desktop_dc = win32gui.GetWindowDC(hdesktop)
        mfc_dc = win32ui.CreateDCFromHandle(desktop_dc)
        save_dc = mfc_dc.CreateCompatibleDC()

        save_bmp = win32ui.CreateBitmap()
        save_bmp.CreateCompatibleBitmap(mfc_dc, w, h)
        save_dc.SelectObject(save_bmp)

        # BitBlt copy vùng từ màn hình
        save_dc.BitBlt((0, 0), (w, h), mfc_dc, (left, top), win32con.SRCCOPY)

        bmpinfo = save_bmp.GetInfo()
        bmpstr = save_bmp.GetBitmapBits(True)
        im = Image.frombuffer(
            "RGB",
            (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
            bmpstr,
            "raw",
            "BGRX",
            0,
            1,
        )

        win32gui.DeleteObject(save_bmp.GetHandle())
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hdesktop, desktop_dc)

        return im

    except Exception as e:
        print(f"Lỗi khi chụp vùng: {e}")
        return None


def capture_region(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    base_folder: str,
    file_prefix: str = "region",
) -> str | None:
    """
    Chụp vùng màn hình xác định bởi (x1, y1) -> (x2, y2) (tọa độ màn hình tuyệt đối).
    Trả về đường dẫn file ảnh nếu thành công, None nếu thất bại.
    """
    im = grab_region(x1, y1, x2, y2)
    if im is None:
        return None

    w, h = im.size
    return _save_image(im, base_folder, file_prefix, label=f"({w}x{h})")


def capture_desktop(
    base_folder: str,
    file_prefix: str = "desktop",
) -> str | None:
    """
    Chụp toàn bộ desktop (tất cả màn hình ảo, bao gồm nhiều monitor).
    Trả về đường dẫn file ảnh nếu thành công, None nếu thất bại.
    """
    SM_XVIRTUALSCREEN = 76
    SM_YVIRTUALSCREEN = 77
    SM_CXVIRTUALSCREEN = 78
    SM_CYVIRTUALSCREEN = 79

    left = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    top = ctypes.windll.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    width = ctypes.windll.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    height = ctypes.windll.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

    im = grab_region(left, top, left + width, top + height)
    if im is None:
        return None

    w, h = im.size
    return _save_image(im, base_folder, file_prefix, label=f"({w}x{h})")


def save_image(
    im: Image.Image, base_folder: str, file_prefix: str = "capture", label: str = ""
) -> str | None:
    """Lưu một ảnh PIL có sẵn (ví dụ ảnh đã vẽ annotation) vào base_folder/YYYY-MM-DD/."""
    return _save_image(im, base_folder, file_prefix, label)


# ---------------------------------------------------------------------------
# Helper nội bộ
# ---------------------------------------------------------------------------


def _save_image(
    im: Image.Image, base_folder: str, file_prefix: str, label: str = ""
) -> str | None:
    """Lưu ảnh vào thư mục base_folder/YYYY-MM-DD/. Trả về path hoặc None."""
    try:
        config = load_config()
        image_format = config.get("image_format", "PNG")

        current_date = datetime.now().strftime("%Y-%m-%d")
        target_dir = os.path.join(base_folder, current_date)
        os.makedirs(target_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        if image_format == "JPEG":
            ext = "jpg"
            save_kwargs = {"quality": config.get("jpeg_quality", 95)}
            if im.mode != "RGB":
                im = im.convert("RGB")
        else:
            ext = "png"
            save_kwargs = {"compress_level": config.get("png_compress_level", 6)}

        out_path = os.path.join(target_dir, f"{file_prefix}_{timestamp}.{ext}")
        im.save(out_path, format=image_format, **save_kwargs)

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Đã lưu {label} -> {out_path}")
        return out_path

    except Exception as e:
        print(f"Lỗi khi lưu ảnh: {e}")
        return None
