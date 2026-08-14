"""أدوات المعالجة: PDF، الصور، OCR، التحويلات."""
import io
import os
import re
import zipfile
from typing import List, Tuple

import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from config import MAX_IMAGES_PER_PDF, MIN_IMAGE_SIDE, OCR_LANGS


# ---------------- PDF ----------------
def pdf_extract_images(pdf_bytes: bytes) -> List[Tuple[str, bytes]]:
    """استخراج كل الصور المضمّنة في ملف PDF (بما فيها الصور التي تحوي كتابة)."""
    out: List[Tuple[str, bytes]] = []
    seen = set()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for pno in range(doc.page_count):
            for img in doc[pno].get_images(full=True):
                xref = img[0]
                if xref in seen:
                    continue
                seen.add(xref)
                try:
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n - pix.alpha >= 4:  # CMYK -> RGB
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    if pix.width < MIN_IMAGE_SIDE or pix.height < MIN_IMAGE_SIDE:
                        continue
                    out.append((f"p{pno+1}_{xref}.png", pix.tobytes("png")))
                    pix = None
                except Exception:
                    continue
                if len(out) >= MAX_IMAGES_PER_PDF:
                    return out
    finally:
        doc.close()
    return out


def pdf_pages_to_images(pdf_bytes: bytes, dpi: int = 150, limit: int = 30) -> List[Tuple[str, bytes]]:
    """تحويل صفحات PDF إلى صور كاملة."""
    out = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for pno in range(min(doc.page_count, limit)):
            pix = doc[pno].get_pixmap(dpi=dpi)
            out.append((f"page_{pno+1}.png", pix.tobytes("png")))
    finally:
        doc.close()
    return out


def pdf_extract_text(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return "\n\n".join(page.get_text() for page in doc).strip()
    finally:
        doc.close()


def pdf_info(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        m = doc.metadata or {}
        imgs = sum(len(doc[i].get_images(full=True)) for i in range(doc.page_count))
        return (
            f"📄 الصفحات: {doc.page_count}\n"
            f"🖼 الصور المضمّنة: {imgs}\n"
            f"🔐 مشفّر: {'نعم' if doc.is_encrypted else 'لا'}\n"
            f"العنوان: {m.get('title') or '-'}\n"
            f"المؤلف: {m.get('author') or '-'}\n"
            f"المنتج: {m.get('producer') or '-'}"
        )
    finally:
        doc.close()


def pdf_split(pdf_bytes: bytes, start: int, end: int) -> bytes:
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    dst = fitz.open()
    try:
        dst.insert_pdf(src, from_page=max(0, start - 1), to_page=min(src.page_count - 1, end - 1))
        return dst.tobytes()
    finally:
        src.close()
        dst.close()


def pdf_merge(files: List[bytes]) -> bytes:
    dst = fitz.open()
    try:
        for b in files:
            with fitz.open(stream=b, filetype="pdf") as s:
                dst.insert_pdf(s)
        return dst.tobytes()
    finally:
        dst.close()


def images_to_pdf(images: List[bytes]) -> bytes:
    pil = [Image.open(io.BytesIO(b)).convert("RGB") for b in images]
    buf = io.BytesIO()
    pil[0].save(buf, format="PDF", save_all=True, append_images=pil[1:])
    return buf.getvalue()


def text_to_pdf(text: str) -> bytes:
    """PDF نصي بسيط (يدعم العربية كنص مرسوم عبر صفحة PyMuPDF)."""
    doc = fitz.open()
    lines = text.splitlines() or [""]
    per_page = 48
    for i in range(0, len(lines), per_page):
        page = doc.new_page()
        chunk = "\n".join(lines[i : i + per_page])
        page.insert_textbox(fitz.Rect(40, 40, 555, 800), chunk, fontsize=11, fontname="helv")
    data = doc.tobytes()
    doc.close()
    return data


# ---------------- OCR والصور ----------------
def _prep(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img).convert("L")
    if max(img.size) < 1000:
        img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(1.8)
    return img.filter(ImageFilter.SHARPEN)


def ocr_image(data: bytes, langs: str = OCR_LANGS) -> str:
    img = _prep(Image.open(io.BytesIO(data)))
    try:
        return pytesseract.image_to_string(img, lang=langs).strip()
    except pytesseract.TesseractError:
        return pytesseract.image_to_string(img).strip()


def image_info(data: bytes) -> str:
    img = Image.open(io.BytesIO(data))
    return (
        f"🖼 الأبعاد: {img.width}×{img.height}\n"
        f"الصيغة: {img.format}\n"
        f"النمط: {img.mode}\n"
        f"الحجم: {len(data)/1024:.1f} KB"
    )


def image_transform(data: bytes, op: str, value: str = "") -> Tuple[bytes, str]:
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    ext = "png"
    if op == "gray":
        img = img.convert("L")
    elif op == "rotate":
        img = img.rotate(-int(value or 90), expand=True)
    elif op == "resize":
        w = int(value or 800)
        img = img.resize((w, int(img.height * w / img.width)), Image.LANCZOS)
    elif op == "compress":
        img = img.convert("RGB")
        ext = "jpg"
    elif op == "invert":
        img = ImageOps.invert(img.convert("RGB"))
    elif op == "enhance":
        img = ImageEnhance.Sharpness(ImageEnhance.Contrast(img.convert("RGB")).enhance(1.5)).enhance(2)
    buf = io.BytesIO()
    img.save(buf, format="JPEG" if ext == "jpg" else "PNG", quality=70, optimize=True)
    return buf.getvalue(), ext


def make_zip(files: List[Tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            z.writestr(name, data)
    return buf.getvalue()


# ---------------- نصوص ----------------
AR_DIAC = re.compile(r"[\u0617-\u061A\u064B-\u0652\u0640]")


def clean_text(t: str) -> str:
    t = AR_DIAC.sub("", t)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def text_stats(t: str) -> str:
    words = re.findall(r"\w+", t, re.UNICODE)
    return (
        f"🔠 الأحرف: {len(t)}\n"
        f"📝 الكلمات: {len(words)}\n"
        f"📄 الأسطر: {len(t.splitlines())}\n"
        f"⏱ زمن القراءة: ~{max(1, len(words)//200)} دقيقة"
    )


def summarize(t: str, n: int = 5) -> str:
    """تلخيص استخراجي بسيط بترجيح تكرار الكلمات."""
    sents = [s.strip() for s in re.split(r"(?<=[.!؟?\n])\s+", t) if len(s.strip()) > 25]
    if len(sents) <= n:
        return t
    words = re.findall(r"\w+", t.lower(), re.UNICODE)
    freq = {}
    for w in words:
        if len(w) > 3:
            freq[w] = freq.get(w, 0) + 1
    scored = sorted(
        sents,
        key=lambda s: sum(freq.get(w, 0) for w in re.findall(r"\w+", s.lower(), re.UNICODE)),
        reverse=True,
    )
    top = set(scored[:n])
    return "\n• ".join([""] + [s for s in sents if s in top]).strip()


def keywords(t: str, n: int = 15) -> List[str]:
    words = [w for w in re.findall(r"\w{4,}", t.lower(), re.UNICODE)]
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:n]]


def chunk_text(t: str, size: int = 3800) -> List[str]:
    return [t[i : i + size] for i in range(0, len(t), size)] or ["(فارغ)"]
