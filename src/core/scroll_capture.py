import ctypes
import time

import win32gui
from PIL import Image

from src.core.capture import grab_region, save_image

user32 = ctypes.windll.user32

INPUT_MOUSE = 0
MOUSEEVENTF_WHEEL = 0x0800


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", _INPUT_UNION)]


def _send_wheel_input(delta: int):
    inp = _INPUT(
        type=INPUT_MOUSE,
        union=_INPUT_UNION(
            mi=_MOUSEINPUT(0, 0, delta & 0xFFFFFFFF, MOUSEEVENTF_WHEEL, 0, None)
        ),
    )
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


# ---------------------------------------------------------------------------
# Chụp scrolling: cuộn dần một cửa sổ (vd. trình duyệt) và ghép các đoạn chụp
# thành một ảnh dài duy nhất, giống chụp toàn bộ trang web dài.
# ---------------------------------------------------------------------------

MAX_SEGMENTS = 60  # chặn vòng lặp vô hạn nếu trang không bao giờ dừng cuộn
SCROLL_WAIT_SECONDS = 0.35  # thời gian chờ trang render sau mỗi lần cuộn
SCROLL_WHEEL_DELTA = -360  # ~3 click/bước (âm = cuộn xuống)


def _row_signature(px, y: int, cols: list[int]) -> tuple:
    return tuple(px[x, y] for x in cols)


def _find_overlap(
    top_img: Image.Image,
    bottom_img: Image.Image,
    search_min: int = 1,
    search_max: int | None = None,
) -> int:

    w, h = top_img.size
    seg_h = bottom_img.size[1]

    limit = min(h, seg_h) if search_max is None else min(h, seg_h, search_max)
    band = min(30, limit)
    if band < 1 or limit < search_min:
        return 0

    top_px = top_img.load()
    bottom_px = bottom_img.load()
    assert top_px is not None and bottom_px is not None

    sample_cols = list(range(0, w, max(1, w // 20)))

    def rows(px, y0: int) -> list[tuple]:
        return [_row_signature(px, y0 + dy, sample_cols) for dy in range(band)]

    for overlap in range(limit, max(search_min, band) - 1, -1):
        top_rows = rows(top_px, h - overlap)
        if len(set(top_rows)) <= 1:
            continue

        bottom_rows = rows(bottom_px, 0)
        if top_rows != bottom_rows:
            continue

        # Band biên khớp không đủ để kết luận: nếu cả hai ảnh có một vùng
        # UI tĩnh (thanh tiêu đề, toolbar không cuộn) giống hệt nhau, band ở
        # đúng mép trên/dưới có thể trùng khớp "giả" dù nội dung thật sự
        # không hề chồng lấn. Xác nhận thêm bằng một band thứ hai ở giữa
        # vùng overlap -> chỉ overlap thật mới khớp xuyên suốt như vậy.
        mid = overlap // 2
        if mid >= band:
            mid_top = rows(top_px, h - overlap + mid)
            mid_bottom = rows(bottom_px, mid)
            if mid_top != mid_bottom:
                continue

        return overlap

    return 0


_OVERLAP_SEARCH_WINDOW = (
    60  # +-px quanh overlap ước lượng, khi đã biết tỉ lệ pixel/scroll
)


def _stitch_vertical(segments: list[Image.Image]) -> Image.Image:

    if len(segments) == 1:
        return segments[0]

    w = segments[0].size[0]
    stitched = segments[0]
    last_overlap: int | None = None

    for seg in segments[1:]:
        search_min, search_max = 1, None
        if last_overlap is not None:
            search_min = max(1, last_overlap - _OVERLAP_SEARCH_WINDOW)
            search_max = last_overlap + _OVERLAP_SEARCH_WINDOW

        overlap = _find_overlap(stitched, seg, search_min, search_max)
        if overlap == 0 and search_max is not None:
            # Không khớp trong vùng hẹp quanh ước lượng -> thử lại không giới hạn
            overlap = _find_overlap(stitched, seg)

        if overlap > 0:
            last_overlap = overlap

        new_h = stitched.size[1] + seg.size[1] - overlap
        merged = Image.new("RGB", (w, new_h))
        merged.paste(stitched, (0, 0))
        merged.paste(seg, (0, stitched.size[1] - overlap))
        stitched = merged

    return stitched


def _scroll_window(hwnd: int):
    """Di chuột vào giữa cửa sổ rồi giả lập cuộn chuột thật (SendInput)."""
    left, top, right, bot = win32gui.GetWindowRect(hwnd)
    cx = (left + right) // 2
    cy = (top + bot) // 2

    prev_x, prev_y = win32gui.GetCursorPos()
    user32.SetCursorPos(cx, cy)
    # Chờ hệ thống xử lý SetCursorPos trước khi bắn sự kiện wheel, nếu không
    # message WM_MOUSEWHEEL có thể được dispatch sau khi chuột đã bị trả về
    # vị trí cũ (prev_x, prev_y) -> cuộn nhầm cửa sổ khác (vd. app hiện tại)
    # thay vì cửa sổ target, khiến ảnh không đổi và vòng lặp chụp dừng sớm.
    time.sleep(0.05)
    _send_wheel_input(SCROLL_WHEEL_DELTA)
    time.sleep(0.05)
    user32.SetCursorPos(prev_x, prev_y)


def capture_scrolling_window(
    hwnd: int,
    base_folder: str,
    file_prefix: str = "scroll",
    max_segments: int = MAX_SEGMENTS,
    on_progress=None,
) -> str | None:

    if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
        print("Cửa sổ đã bị đóng hoặc ẩn.")
        return None

    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(0.3)

    left, top, right, bot = win32gui.GetWindowRect(hwnd)
    if right - left <= 0 or bot - top <= 0:
        print("Cửa sổ bị chặn hoặc đang thu nhỏ.")
        return None

    segments: list[Image.Image] = []
    prev_img = None

    for i in range(max_segments):
        img = grab_region(left, top, right, bot)
        if img is None:
            break
        if img.mode != "RGB":
            img = img.convert("RGB")

        if prev_img is not None and img.tobytes() == prev_img.tobytes():
            # Ảnh giống hệt lần trước -> đã cuộn tới cuối trang
            break

        segments.append(img)
        prev_img = img
        if on_progress:
            on_progress(i + 1)

        _scroll_window(hwnd)
        time.sleep(SCROLL_WAIT_SECONDS)

    if not segments:
        return None

    print(f"[Scroll] Đã chụp {len(segments)} đoạn, đang ghép...")
    stitched = _stitch_vertical(segments)
    w, h = stitched.size
    return save_image(stitched, base_folder, file_prefix, label=f"({w}x{h})")
