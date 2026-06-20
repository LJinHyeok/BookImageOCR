from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import fitz
import numpy as np
import pytesseract
from PIL import Image, ImageDraw

try:
    import cv2
except ImportError:  # pragma: no cover - handled at runtime for friendlier errors
    cv2 = None


Progress = Callable[[str], None]


def application_root() -> Path:
    """Return the source directory, or PyInstaller's bundled resource directory."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


@dataclass(frozen=True)
class OcrOptions:
    lang: str = "kor+eng+chi_tra"
    dpi: int = 300
    psm: int = 6
    detect_graphics: bool = True
    graphic_min_area: float = 0.035
    tesseract_cmd: str | None = None
    tessdata_dir: str | None = None


@dataclass(frozen=True)
class RectPx:
    x: int
    y: int
    w: int
    h: int

    @property
    def area(self) -> int:
        return self.w * self.h

    def contains_center(self, x: int, y: int, w: int, h: int) -> bool:
        cx = x + w / 2
        cy = y + h / 2
        return self.x <= cx <= self.x + self.w and self.y <= cy <= self.y + self.h


def find_tesseract(explicit: str | None = None) -> str | None:
    bundled_tesseract = application_root() / "tesseract" / "tesseract.exe"
    candidates: list[str | None] = [
        explicit,
        os.environ.get("TESSERACT_CMD"),
        str(bundled_tesseract),
        shutil.which("tesseract"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(Path(candidate))
    return None


def configure_tesseract(options: OcrOptions) -> None:
    tesseract = find_tesseract(options.tesseract_cmd)
    if not tesseract:
        raise RuntimeError(
            "Tesseract OCR 엔진을 찾지 못했습니다. Tesseract를 설치하거나 "
            "--tesseract 옵션으로 tesseract.exe 경로를 지정하세요."
        )
    pytesseract.pytesseract.tesseract_cmd = tesseract


def find_tessdata_dir(explicit: str | None = None) -> str | None:
    project_tessdata = application_root() / "tessdata"
    candidates = [
        explicit,
        os.environ.get("TESSDATA_PREFIX"),
        str(project_tessdata),
        r"C:\Program Files\Tesseract-OCR\tessdata",
        r"C:\Program Files (x86)\Tesseract-OCR\tessdata",
    ]
    for candidate in candidates:
        if candidate and (Path(candidate) / "eng.traineddata").exists():
            return str(Path(candidate))
    return None


def build_tesseract_config(options: OcrOptions) -> str:
    parts = [f"--psm {options.psm}"]
    tessdata_dir = find_tessdata_dir(options.tessdata_dir)
    if tessdata_dir:
        parts.append(f"--tessdata-dir {tessdata_dir}")
    return " ".join(parts)


def pixmap_to_pil(pix: fitz.Pixmap) -> Image.Image:
    mode = "RGB" if pix.alpha == 0 else "RGBA"
    return Image.frombytes(mode, (pix.width, pix.height), pix.samples).convert("RGB")


def detect_graphic_regions(image: Image.Image, min_area_ratio: float) -> list[RectPx]:
    if cv2 is None:
        return []

    rgb = np.array(image)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    height, width = gray.shape
    page_area = width * height

    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    binary = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 35, 15
    )

    regions: list[RectPx] = []

    def add_candidates(mask: np.ndarray, kernel_w: int, kernel_h: int, predicate: Callable[[RectPx], bool]) -> None:
        merged = cv2.morphologyEx(
            mask,
            cv2.MORPH_CLOSE,
            np.ones((kernel_h, kernel_w), np.uint8),
        )
        contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            region = RectPx(x, y, w, h)
            if region.area / page_area < min_area_ratio:
                continue
            if w < width * 0.18 or h < height * 0.06:
                continue
            if predicate(region):
                regions.append(region)

    # Only very dense monochrome regions are treated as graphics. This avoids
    # joining normal paragraphs into a single large rectangle during masking.
    def is_dense_graphic(region: RectPx) -> bool:
        crop = binary[region.y : region.y + region.h, region.x : region.x + region.w]
        return float(np.count_nonzero(crop)) / region.area >= 0.24

    add_candidates(
        binary,
        max(18, width // 60),
        max(18, height // 80),
        is_dense_graphic,
    )

    # Detect colored graphics independently. Their bounds come from color pixels,
    # not from nearby black body text, so a colored callout cannot swallow the
    # paragraph above or below it.
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    colorful = ((hsv[:, :, 1] > 45) & (hsv[:, :, 2] < 245)).astype(np.uint8) * 255

    def is_color_graphic(region: RectPx) -> bool:
        crop = colorful[region.y : region.y + region.h, region.x : region.x + region.w]
        return float(np.count_nonzero(crop)) / region.area >= 0.05

    add_candidates(
        colorful,
        max(18, width // 40),
        max(18, height // 35),
        is_color_graphic,
    )

    return merge_regions(regions)


def merge_regions(regions: Iterable[RectPx]) -> list[RectPx]:
    merged: list[RectPx] = []
    for region in sorted(regions, key=lambda r: r.area, reverse=True):
        duplicate = False
        for existing in merged:
            if intersection_area(region, existing) / max(1, region.area) > 0.82:
                duplicate = True
                break
        if not duplicate:
            merged.append(region)
    return merged


def mask_regions(image: Image.Image, regions: list[RectPx], margin: int = 8) -> Image.Image:
    if not regions:
        return image

    masked = image.copy()
    draw = ImageDraw.Draw(masked)
    width, height = masked.size
    for region in regions:
        x1 = max(0, region.x - margin)
        y1 = max(0, region.y - margin)
        x2 = min(width, region.x + region.w + margin)
        y2 = min(height, region.y + region.h + margin)
        draw.rectangle((x1, y1, x2, y2), fill="white")
    return masked


def keep_graphic_regions(image: Image.Image, regions: list[RectPx], options: OcrOptions) -> list[RectPx]:
    """Keep only regions that do not read like a substantial text block."""
    config = build_tesseract_config(options)
    graphics: list[RectPx] = []
    for region in regions:
        crop = image.crop((region.x, region.y, region.x + region.w, region.y + region.h))
        try:
            candidate_text = pytesseract.image_to_string(
                crop,
                lang=options.lang,
                config=config,
            )
        except pytesseract.TesseractError:
            # When the extra check cannot run, preserve the original conservative
            # graphic decision instead of risking OCR text inside an illustration.
            graphics.append(region)
            continue
        character_count = len("".join(candidate_text.split()))
        if character_count < 160:
            graphics.append(region)
    return graphics


def intersection_area(a: RectPx, b: RectPx) -> int:
    x1 = max(a.x, b.x)
    y1 = max(a.y, b.y)
    x2 = min(a.x + a.w, b.x + b.w)
    y2 = min(a.y + a.h, b.y + b.h)
    return max(0, x2 - x1) * max(0, y2 - y1)


def make_searchable_pdf(
    input_pdf: Path,
    output_pdf: Path,
    options: OcrOptions,
    progress: Progress | None = None,
) -> None:
    progress = progress or (lambda message: None)
    configure_tesseract(options)

    source = fitz.open(input_pdf)
    result = fitz.open()
    zoom = options.dpi / 72
    matrix = fitz.Matrix(zoom, zoom)

    try:
        for page_index, source_page in enumerate(source, start=1):
            progress(f"{page_index}/{source.page_count} 페이지 렌더링")
            pix = source_page.get_pixmap(matrix=matrix, alpha=False)
            image = pixmap_to_pil(pix)
            page_rect = source_page.rect

            target_page = result.new_page(width=page_rect.width, height=page_rect.height)
            # Reuse the original PDF page as the visible layer. This preserves its
            # already-compressed scan instead of writing a newly rendered, much
            # larger bitmap into the result.
            target_page.show_pdf_page(target_page.rect, source, page_index - 1)

            graphics = (
                detect_graphic_regions(image, options.graphic_min_area)
                if options.detect_graphics
                else []
            )
            if graphics:
                graphics = keep_graphic_regions(image, graphics, options)
            progress(f"{page_index}/{source.page_count} 페이지 OCR")
            config = build_tesseract_config(options)
            ocr_image = mask_regions(image, graphics)
            ocr_pdf = pytesseract.image_to_pdf_or_hocr(
                ocr_image,
                lang=options.lang,
                config=config,
                extension="pdf",
            )
            overlay_doc = fitz.open("pdf", ocr_pdf)
            try:
                overlay_page = overlay_doc[0]
                # Tesseract's PDF contains a copy of the OCR source image plus text.
                # Keep only its text layer, then draw the original page image below.
                for image_info in overlay_page.get_images(full=True):
                    overlay_page.delete_image(image_info[0])
                target_page.show_pdf_page(target_page.rect, overlay_doc, 0, overlay=True)
            finally:
                overlay_doc.close()
            progress(
                f"{page_index}/{source.page_count} 페이지 완료: "
                f"제외 그림 영역 {len(graphics)}개"
            )

        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        result.save(output_pdf, garbage=4, deflate=True)
    finally:
        result.close()
        source.close()


def run_gui() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("Book Image OCR PDF")
    root.geometry("680x430")
    root.minsize(640, 400)

    input_var = tk.StringVar()
    output_var = tk.StringVar()
    lang_var = tk.StringVar(value="kor+eng+chi_tra")
    dpi_var = tk.IntVar(value=300)
    tesseract_var = tk.StringVar(value=find_tesseract() or "")
    detect_var = tk.BooleanVar(value=True)
    status_var = tk.StringVar(value="PDF를 선택하세요.")
    progress_var = tk.DoubleVar(value=0)
    timing_var = tk.StringVar(value="")
    started_at: float | None = None

    def format_duration(seconds: float) -> str:
        total_seconds = max(0, round(seconds))
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02}"

    def choose_input() -> None:
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if not path:
            return
        input_var.set(path)
        if not output_var.get():
            src = Path(path)
            output_var.set(str(src.with_name(src.stem + "_searchable.pdf")))

    def choose_output() -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")]
        )
        if path:
            output_var.set(path)

    def choose_tesseract() -> None:
        path = filedialog.askopenfilename(filetypes=[("Tesseract", "tesseract.exe")])
        if path:
            tesseract_var.set(path)

    def set_status(message: str) -> None:
        def update() -> None:
            status_var.set(message)
            match = re.match(r"(\d+)/(\d+)", message)
            if not match or started_at is None:
                return
            current_page, total_pages = map(int, match.groups())
            progress_var.set(current_page / total_pages * 100)
            elapsed = time.monotonic() - started_at
            remaining = elapsed / max(1, current_page) * (total_pages - current_page)
            timing_var.set(
                f"{current_page}/{total_pages} pages | elapsed {format_duration(elapsed)} | ETA {format_duration(remaining)}"
            )

        root.after(0, update)

    def start() -> None:
        nonlocal started_at
        if not input_var.get() or not output_var.get():
            messagebox.showwarning("확인 필요", "입력 PDF와 출력 PDF를 선택하세요.")
            return

        start_button.configure(state="disabled")
        started_at = time.monotonic()
        progress_var.set(0)
        timing_var.set("Preparing OCR...")

        def worker() -> None:
            try:
                options = OcrOptions(
                    lang=lang_var.get().strip() or "kor+eng+chi_tra",
                    dpi=int(dpi_var.get()),
                    detect_graphics=bool(detect_var.get()),
                    tesseract_cmd=tesseract_var.get().strip() or None,
                )
                make_searchable_pdf(
                    Path(input_var.get()),
                    Path(output_var.get()),
                    options,
                    progress=set_status,
                )
            except Exception as exc:  # noqa: BLE001 - GUI needs a friendly boundary
                root.after(0, lambda: messagebox.showerror("실패", str(exc)))
                set_status("실패했습니다.")
            else:
                set_status("완료했습니다.")
                root.after(0, lambda: messagebox.showinfo("완료", "검색 가능한 PDF를 만들었습니다."))
            finally:
                root.after(0, lambda: start_button.configure(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    pad = {"padx": 12, "pady": 7}
    frame = ttk.Frame(root, padding=14)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(1, weight=1)

    ttk.Label(frame, text="입력 PDF").grid(row=0, column=0, sticky="w", **pad)
    ttk.Entry(frame, textvariable=input_var).grid(row=0, column=1, sticky="ew", **pad)
    ttk.Button(frame, text="찾기", command=choose_input).grid(row=0, column=2, **pad)

    ttk.Label(frame, text="출력 PDF").grid(row=1, column=0, sticky="w", **pad)
    ttk.Entry(frame, textvariable=output_var).grid(row=1, column=1, sticky="ew", **pad)
    ttk.Button(frame, text="저장 위치", command=choose_output).grid(row=1, column=2, **pad)

    ttk.Label(frame, text="언어").grid(row=2, column=0, sticky="w", **pad)
    ttk.Entry(frame, textvariable=lang_var, width=18).grid(row=2, column=1, sticky="w", **pad)

    ttk.Label(frame, text="DPI").grid(row=3, column=0, sticky="w", **pad)
    ttk.Spinbox(frame, from_=150, to=450, increment=50, textvariable=dpi_var, width=8).grid(
        row=3, column=1, sticky="w", **pad
    )

    ttk.Label(frame, text="Tesseract").grid(row=5, column=0, sticky="w", **pad)
    ttk.Entry(frame, textvariable=tesseract_var).grid(row=5, column=1, sticky="ew", **pad)
    ttk.Button(frame, text="찾기", command=choose_tesseract).grid(row=5, column=2, **pad)

    ttk.Checkbutton(
        frame,
        text="그림/도표 영역 안의 OCR 글자는 제외",
        variable=detect_var,
    ).grid(row=6, column=1, sticky="w", **pad)

    start_button = ttk.Button(frame, text="PDF 만들기", command=start)
    start_button.grid(row=7, column=1, sticky="e", **pad)

    ttk.Separator(frame).grid(row=8, column=0, columnspan=3, sticky="ew", pady=12)
    ttk.Label(frame, textvariable=status_var).grid(row=9, column=0, columnspan=3, sticky="w", **pad)
    ttk.Progressbar(frame, variable=progress_var, maximum=100, mode="determinate").grid(
        row=10, column=0, columnspan=3, sticky="ew", padx=12, pady=(4, 0)
    )
    ttk.Label(frame, textvariable=timing_var).grid(row=11, column=0, columnspan=3, sticky="w", **pad)

    root.mainloop()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="스캔 이미지 PDF를 검색 가능한 PDF로 변환합니다.")
    parser.add_argument("input", nargs="?", help="입력 PDF")
    parser.add_argument("output", nargs="?", help="출력 PDF")
    parser.add_argument(
        "--lang",
        default="kor+eng+chi_tra",
        help="Tesseract 언어 코드, 예: kor+eng+chi_tra",
    )
    parser.add_argument("--dpi", type=int, default=300, help="OCR 렌더링 DPI")
    parser.add_argument("--psm", type=int, default=6, help="Tesseract page segmentation mode")
    parser.add_argument("--tesseract", help="tesseract.exe 경로")
    parser.add_argument("--tessdata-dir", help="Tesseract 언어 데이터 폴더 경로")
    parser.add_argument("--no-detect-graphics", action="store_true", help="그림 영역 자동 제외 끄기")
    parser.add_argument(
        "--graphic-min-area",
        type=float,
        default=0.035,
        help="그림 후보로 볼 최소 페이지 면적 비율",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if not args.input and not args.output:
        run_gui()
        return 0
    if not args.input or not args.output:
        print("입력 PDF와 출력 PDF를 모두 지정하세요.", file=sys.stderr)
        return 2

    options = OcrOptions(
        lang=args.lang,
        dpi=args.dpi,
        psm=args.psm,
        detect_graphics=not args.no_detect_graphics,
        graphic_min_area=args.graphic_min_area,
        tesseract_cmd=args.tesseract,
        tessdata_dir=args.tessdata_dir,
    )
    make_searchable_pdf(Path(args.input), Path(args.output), options, progress=print)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
