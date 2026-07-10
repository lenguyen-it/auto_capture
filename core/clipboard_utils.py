import io

import win32clipboard
from PIL import Image


def copy_image_to_clipboard(im: Image.Image) -> None:
    """
    Copy ảnh PIL vào clipboard Windows dưới dạng CF_DIB.
    Ảnh sau đó có thể dán (Ctrl+V) vào Paint, Word, Zalo, v.v.
    """
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "BMP")
    # CF_DIB = nội dung file BMP bỏ 14 byte BITMAPFILEHEADER đầu
    data = buf.getvalue()[14:]

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
    finally:
        win32clipboard.CloseClipboard()
