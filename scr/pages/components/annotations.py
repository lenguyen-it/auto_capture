import math
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Cấu hình mặc định của annotation
# ---------------------------------------------------------------------------

COLOR = "#ff3b30"
LINE_WIDTH = 4  # ~1mm trên màn hình 96 DPI
FONT_FAMILY = "Arial"
FONT_SIZE = 12  # cỡ 12, chữ bình thường (không đậm/nghiêng)
FONT_SIZE_PX = 16  # 12pt xấp xỉ 16px khi render bằng PIL ở 96 DPI
ARROW_SHAPE = (14, 17, 6)  # arrowshape của canvas: (d1, d2, d3)
MIN_DRAG = 3  # px, kéo nhỏ hơn ngưỡng này thì bỏ qua (coi như click nhầm)

# Cursor tương ứng với từng tool
TOOL_CURSORS = {
    "pen": "pencil",
    "text": "xterm",
    "rect": "cross",
    "arrow": "cross",
}


class AnnotationLayer:
    """
    Quản lý các annotation (pen / text / rect / arrow) vẽ đè lên canvas
    của RegionSelector

    - Toạ độ lưu theo hệ toạ độ canvas (canvas fullscreen tại +0+0).
    - Chỉ cho vẽ bên trong vùng chọn (set_region).
    - Hỗ trợ undo (xoá annotation mới nhất) và render toàn bộ ra ảnh PIL.
    """

    def __init__(self, canvas: tk.Canvas):
        self.canvas = canvas
        self.tool: str | None = None
        self.region: tuple[int, int, int, int] | None = None

        # Stack các annotation đã hoàn thành (phục vụ undo + render)
        self._records: list[dict] = []
        # Trạng thái thao tác kéo đang diễn ra
        self._drag: dict | None = None
        # Ô nhập text đang mở (nếu có)
        self._entry: tk.Entry | None = None
        self._entry_item: int | None = None
        self._entry_pos: tuple[int, int] | None = None

    # ------------------------------------------------------------------
    # Trạng thái tool / vùng vẽ
    # ------------------------------------------------------------------

    def set_tool(self, tool: str | None):
        self.commit_text()
        self.tool = tool
        if tool is None:
            cursor = "cross"
        else:
            cursor = TOOL_CURSORS.get(tool, "cross")
        self.canvas.configure(cursor=cursor)

    def set_region(self, region: tuple[int, int, int, int]):
        self.region = region

    def clear(self):
        """Xoá toàn bộ annotation (khi người dùng kéo chọn vùng mới)."""
        self._cancel_entry()
        for rec in self._records:
            for item in rec["items"]:
                self.canvas.delete(item)
        self._records.clear()
        self._drag = None

    def undo(self):
        # Nếu đang gõ text thì huỷ ô nhập thay vì xoá annotation trước đó
        if self._entry is not None:
            self._cancel_entry()
            return
        if self._records:
            rec = self._records.pop()
            for item in rec["items"]:
                self.canvas.delete(item)

    # ------------------------------------------------------------------
    # Sự kiện chuột — trả về True nếu đã xử lý (đang có tool được chọn)
    # ------------------------------------------------------------------

    def on_press(self, x: int, y: int) -> bool:
        if self.tool is None or self.region is None:
            return False

        if not self._inside(x, y):
            # Có tool nhưng click ngoài vùng chọn: nuốt sự kiện, không vẽ
            self.commit_text()
            return True

        if self.tool == "text":
            self.commit_text()
            self._open_entry(x, y)
            return True

        x, y = self._clamp(x, y)
        self._drag = {
            "type": self.tool,
            "start": (x, y),
            "points": [(x, y)],
            "item": None,
        }
        return True

    def on_drag(self, x: int, y: int) -> bool:
        if self.tool is None:
            return False
        if self._drag is None:
            return True

        x, y = self._clamp(x, y)
        d = self._drag
        x0, y0 = d["start"]

        if d["item"]:
            self.canvas.delete(d["item"])
            d["item"] = None

        if d["type"] == "pen":
            d["points"].append((x, y))
            if len(d["points"]) >= 2:
                flat = [c for p in d["points"] for c in p]
                d["item"] = self.canvas.create_line(
                    *flat,
                    fill=COLOR,
                    width=LINE_WIDTH,
                    capstyle="round",
                    joinstyle="round",
                    smooth=True,
                )
        elif d["type"] == "rect":
            d["item"] = self.canvas.create_rectangle(
                x0, y0, x, y, outline=COLOR, width=LINE_WIDTH
            )
        elif d["type"] == "arrow":
            d["item"] = self.canvas.create_line(
                x0,
                y0,
                x,
                y,
                fill=COLOR,
                width=LINE_WIDTH,
                arrow=tk.LAST,
                arrowshape=ARROW_SHAPE,
                capstyle="round",
            )
        return True

    def on_release(self, x: int, y: int) -> bool:
        if self.tool is None:
            return False

        d, self._drag = self._drag, None
        if d is None:
            return True

        x, y = self._clamp(x, y)
        x0, y0 = d["start"]

        too_small = abs(x - x0) < MIN_DRAG and abs(y - y0) < MIN_DRAG
        if d["type"] == "pen":
            too_small = len(d["points"]) < 2

        if too_small or d["item"] is None:
            if d["item"]:
                self.canvas.delete(d["item"])
            return True

        rec: dict = {"type": d["type"], "items": [d["item"]]}
        if d["type"] == "pen":
            rec["points"] = d["points"]
        else:
            rec["coords"] = (x0, y0, x, y)
        self._records.append(rec)
        return True

    # ------------------------------------------------------------------
    # Tool text: ô nhập trực tiếp trên canvas
    # ------------------------------------------------------------------

    def _open_entry(self, x: int, y: int):
        entry = tk.Entry(
            self.canvas,
            font=(FONT_FAMILY, FONT_SIZE),
            fg=COLOR,
            insertbackground=COLOR,
            relief="solid",
            bd=1,
            width=8,
        )
        self._entry = entry
        self._entry_pos = (x, y)
        self._entry_item = self.canvas.create_window(x, y, window=entry, anchor="nw")
        entry.focus_set()

        entry.bind("<Return>", lambda _e: self.commit_text())
        # "break" để Escape/Ctrl+Z không lan lên overlay (đóng overlay / undo nhầm)
        entry.bind("<Escape>", self._on_entry_escape)
        entry.bind("<Control-z>", lambda _e: "break")
        entry.bind("<KeyRelease>", self._auto_resize_entry)
        entry.bind("<FocusOut>", lambda _e: self.commit_text())

    def _on_entry_escape(self, _event):
        self._cancel_entry()
        return "break"

    def _auto_resize_entry(self, _event=None):
        if self._entry is not None:
            self._entry.config(width=max(8, len(self._entry.get()) + 2))

    def commit_text(self):
        """Chốt nội dung ô nhập text đang mở thành annotation trên canvas."""
        if self._entry is None:
            return

        # SỬA LỖI 2: Assert để Pylance biết chắc chắn _entry_pos không phải None
        assert (
            self._entry_pos is not None
        ), "_entry_pos cannot be None when _entry exists"

        text = self._entry.get().strip()
        x, y = self._entry_pos
        self._cancel_entry()
        if not text:
            return

        item = self.canvas.create_text(
            x + 3,
            y + 3,
            text=text,
            fill=COLOR,
            font=(FONT_FAMILY, FONT_SIZE),
            anchor="nw",
        )
        self._records.append(
            {"type": "text", "items": [item], "pos": (x + 3, y + 3), "text": text}
        )

    def _cancel_entry(self):
        if self._entry is None:
            return
        entry, item = self._entry, self._entry_item
        # Reset trước khi destroy để <FocusOut> phát sinh lúc destroy không re-commit
        self._entry = None
        self._entry_item = None
        self._entry_pos = None

        # SỬA LỖI 3: Kiểm tra item có tồn tại hợp lệ hay không trước khi gọi .delete()
        if item is not None:
            self.canvas.delete(item)
        entry.destroy()

    # ------------------------------------------------------------------
    # Render annotation ra ảnh PIL (ảnh crop của vùng chọn)
    # ------------------------------------------------------------------

    def render_to_image(
        self, im: Image.Image, offset: tuple[int, int] = (0, 0)
    ) -> Image.Image:
        """
        Vẽ toàn bộ annotation lên ảnh `im`.
        `offset` = toạ độ canvas của góc trên-trái vùng chọn (để đổi hệ toạ độ).
        """
        self.commit_text()
        if not self._records:
            return im

        draw = ImageDraw.Draw(im)
        try:
            font = ImageFont.truetype("arial.ttf", FONT_SIZE_PX)
        except OSError:
            font = ImageFont.load_default()

        ox, oy = offset
        for rec in self._records:
            if rec["type"] == "pen":
                pts = [(px - ox, py - oy) for px, py in rec["points"]]
                draw.line(pts, fill=COLOR, width=LINE_WIDTH, joint="curve")
            elif rec["type"] == "rect":
                x1, y1, x2, y2 = rec["coords"]
                box = (
                    min(x1, x2) - ox,
                    min(y1, y2) - oy,
                    max(x1, x2) - ox,
                    max(y1, y2) - oy,
                )
                draw.rectangle(box, outline=COLOR, width=LINE_WIDTH)
            elif rec["type"] == "arrow":
                x1, y1, x2, y2 = rec["coords"]
                self._draw_arrow(draw, x1 - ox, y1 - oy, x2 - ox, y2 - oy)
            elif rec["type"] == "text":
                x, y = rec["pos"]
                draw.text((x - ox, y - oy), rec["text"], fill=COLOR, font=font)
        return im

    @staticmethod
    def _draw_arrow(draw: ImageDraw.ImageDraw, x1, y1, x2, y2):
        draw.line((x1, y1, x2, y2), fill=COLOR, width=LINE_WIDTH)

        ang = math.atan2(y2 - y1, x2 - x1)
        head = max(ARROW_SHAPE[1], LINE_WIDTH * 3)
        spread = math.radians(22)
        p1 = (x2 - head * math.cos(ang - spread), y2 - head * math.sin(ang - spread))
        p2 = (x2 - head * math.cos(ang + spread), y2 - head * math.sin(ang + spread))
        draw.polygon([(x2, y2), p1, p2], fill=COLOR)

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _inside(self, x: int, y: int) -> bool:
        # SỬA LỖI 4 & 5: Thêm guard clause phòng trường hợp hàm này bị gọi riêng lẻ khi chưa có vùng chọn
        if self.region is None:
            return False
        x1, y1, x2, y2 = self.region
        return x1 <= x <= x2 and y1 <= y <= y2

    def _clamp(self, x: int, y: int) -> tuple[int, int]:
        # SỬA LỖI 4 & 5: Đảm bảo self.region tồn tại trước khi unpack
        if self.region is None:
            return x, y
        x1, y1, x2, y2 = self.region
        return min(max(x, x1), x2), min(max(y, y1), y2)
