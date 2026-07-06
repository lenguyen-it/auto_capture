import os
import ctypes
from datetime import datetime
from PIL import Image
import win32gui
import win32ui
import win32con

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

        return _save_image(im, base_folder, file_prefix, label=f"({w}x{h})")

    except Exception as e:
        print(f"Lỗi khi chụp vùng: {e}")
        return None


# ---------------------------------------------------------------------------
# Helper nội bộ
# ---------------------------------------------------------------------------


def _save_image(
    im: Image.Image, base_folder: str, file_prefix: str, label: str = ""
) -> str | None:
    """Lưu ảnh vào thư mục base_folder/YYYY-MM-DD/. Trả về path hoặc None."""
    try:
        current_date = datetime.now().strftime("%Y-%m-%d")
        target_dir = os.path.join(base_folder, current_date)
        os.makedirs(target_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = os.path.join(target_dir, f"{file_prefix}_{timestamp}.png")
        im.save(out_path)

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Đã lưu {label} -> {out_path}")
        return out_path

    except Exception as e:
        print(f"Lỗi khi lưu ảnh: {e}")
        return None
