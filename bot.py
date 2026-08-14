"""
بوت تلجرام: استخراج صور من PDF + OCR للنصوص + ترجمة عبر قاموس يلقّنه الأدمن
+ أكثر من 20 مهمة إضافية.

قبل التشغيل: املأ BOT_TOKEN و ADMIN_ID في ملف config.py
"""
import asyncio
import io
import logging
import os
import re
import time
from datetime import datetime

import qrcode
from telegram import InputMediaPhoto, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import storage as st
import tools as T
from config import ADMIN_ID, BOT_TOKEN, OCR_LANGS

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", level=logging.INFO
)
log = logging.getLogger("bot")

START_TIME = time.time()

HELP = """<b>🤖 قائمة الأوامر</b>

<b>📄 ملفات PDF</b>
أرسل ملف PDF مباشرة → تُستخرج كل الصور وتُرسل لك.
/pdfmode <code>images|pages|text|zip|info</code> — طريقة معالجة الـ PDF القادم
/split <code>من الى</code> — اقتطاع صفحات من آخر PDF أرسلته
/topdf — تحويل الصور المخزّنة إلى ملف PDF
/merge — دمج ملفات PDF المخزّنة
/clearfiles — تفريغ الملفات المؤقتة

<b>🖼 الصور و OCR</b>
أرسل صورة → يُستخرج نصّها تلقائياً.
/ocrlang <code>ara+eng</code> — تغيير لغات الـ OCR
/img <code>gray|rotate 90|resize 800|compress|invert|enhance</code> — تعديل آخر صورة
/imginfo — معلومات آخر صورة

<b>🌐 الترجمة بالقاموس المُلقَّن</b>
/pair <code>ar-&gt;en</code> — اختيار زوج اللغة
/tr <code>النص</code> — ترجمة نص
/trlast — ترجمة آخر نص مُستخرج
/pairs — أزواج اللغات المتوفرة
/dict <code>كلمة</code> — البحث في القاموس

<b>🧰 أدوات النص</b>
/stats <code>نص</code> — إحصائيات
/sum <code>نص</code> — تلخيص
/keys <code>نص</code> — كلمات مفتاحية
/clean <code>نص</code> — تنظيف النص
/txt — تحويل آخر نص إلى ملف .txt
/txtpdf — تحويل آخر نص إلى PDF
/qr <code>نص</code> — توليد رمز QR
/note <code>عنوان | محتوى</code> — حفظ ملاحظة
/notes /getnote <code>id</code> /delnote <code>id</code>

<b>ℹ️ عام</b>
/start /help /id /ping /about

<b>👑 للأدمن</b>
/teach <code>ar-&gt;en</code> ثم أرسل ملف/نص القاموس
/teachtext <code>ar-&gt;en</code>
<code>كلمة = translation</code>
/delpair <code>ar-&gt;en</code> — حذف زوج
/exportdict <code>ar-&gt;en</code> — تصدير القاموس
/broadcast <code>رسالة</code> — إذاعة
/ban <code>id</code> /unban <code>id</code>
/admin — إحصائيات البوت
"""


# ---------------- مساعدات ----------------
def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


def ud(ctx: ContextTypes.DEFAULT_TYPE) -> dict:
    return ctx.user_data


async def send_long(update: Update, text: str, title: str = ""):
    parts = T.chunk_text(text)
    for i, p in enumerate(parts[:10]):
        head = f"<b>{title}</b> ({i+1}/{min(len(parts),10)})\n" if title else ""
        await update.message.reply_text(head + f"<pre>{_esc(p)}</pre>", parse_mode=ParseMode.HTML)
    if len(parts) > 10:
        bio = io.BytesIO(text.encode("utf-8"))
        bio.name = "full_text.txt"
        await update.message.reply_document(bio, caption="النص كاملاً 📄")


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def guard(update: Update) -> bool:
    u = update.effective_user
    st.touch_user(u.id, u.username or "")
    if st.is_banned(u.id) and not is_admin(u.id):
        await update.message.reply_text("🚫 تم حظرك من استخدام البوت.")
        return False
    return True


# ---------------- أوامر عامة ----------------
async def cmd_start(update: Update, ctx):
    if not await guard(update):
        return
    await update.message.reply_text(
        "👋 أهلاً بك!\n\n"
        "أرسل لي ملف <b>PDF</b> لأستخرج كل الصور منه، أو أرسل <b>صورة</b> لأستخرج نصّها، "
        "أو استعمل <code>/tr</code> للترجمة بالقاموس المُلقَّن.\n\n"
        "اكتب /help لكل الأوامر.",
        parse_mode=ParseMode.HTML,
    )


async def cmd_help(update: Update, ctx):
    await update.message.reply_text(HELP, parse_mode=ParseMode.HTML)


async def cmd_id(update: Update, ctx):
    await update.message.reply_text(
        f"🆔 أيديك: <code>{update.effective_user.id}</code>\n"
        f"💬 أيدي المحادثة: <code>{update.effective_chat.id}</code>",
        parse_mode=ParseMode.HTML,
    )


async def cmd_ping(update: Update, ctx):
    t0 = time.perf_counter()
    m = await update.message.reply_text("🏓 ...")
    up = int(time.time() - START_TIME)
    await m.edit_text(
        f"🏓 Pong — {(time.perf_counter()-t0)*1000:.0f}ms\n"
        f"⏱ مدة التشغيل: {up//3600}س {(up%3600)//60}د"
    )


async def cmd_about(update: Update, ctx):
    s = st.stats()
    await update.message.reply_text(
        f"🤖 بوت PDF + OCR + ترجمة بالقاموس\n"
        f"👥 المستخدمون: {s['users']}\n"
        f"⚙️ العمليات: {s['jobs']}\n"
        f"🗣 لغات OCR: {OCR_LANGS}\n"
        f"📅 {datetime.utcnow():%Y-%m-%d}"
    )


# ---------------- PDF ----------------
async def cmd_pdfmode(update: Update, ctx):
    mode = (ctx.args[0] if ctx.args else "").lower()
    if mode not in {"images", "pages", "text", "zip", "info"}:
        await update.message.reply_text("الاستعمال: /pdfmode images|pages|text|zip|info")
        return
    ud(ctx)["pdfmode"] = mode
    await update.message.reply_text(f"✅ وضع معالجة PDF: <b>{mode}</b>", parse_mode=ParseMode.HTML)


async def on_document(update: Update, ctx):
    if not await guard(update):
        return
    doc = update.message.document
    name = (doc.file_name or "file").lower()

    # الأدمن في وضع تلقين القاموس
    if is_admin(update.effective_user.id) and ud(ctx).get("teach_pair"):
        f = await doc.get_file()
        data = bytes(await f.download_as_bytearray())
        text = _decode(data)
        await _absorb_glossary(update, ctx, text)
        return

    if doc.file_size and doc.file_size > 45 * 1024 * 1024:
        await update.message.reply_text("⚠️ الملف كبير جداً (الحد 45MB).")
        return

    f = await doc.get_file()
    data = bytes(await f.download_as_bytearray())

    if name.endswith(".txt"):
        text = _decode(data)
        ud(ctx)["last_text"] = text
        await send_long(update, text, "📄 محتوى الملف")
        return

    if not name.endswith(".pdf"):
        await update.message.reply_text("أرسل ملف PDF أو صورة أو ملف نصي 📎")
        return

    ud(ctx)["last_pdf"] = data
    ud(ctx).setdefault("pdfs", []).append(data)
    st.bump_jobs(update.effective_user.id)
    mode = ud(ctx).get("pdfmode", "images")

    await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_PHOTO)

    if mode == "info":
        await update.message.reply_text(T.pdf_info(data))
        return

    if mode == "text":
        text = T.pdf_extract_text(data)
        if not text:
            await update.message.reply_text("لا يوجد نص محدد — سأجرّب OCR على الصفحات…")
            pages = T.pdf_pages_to_images(data, limit=10)
            text = "\n\n".join(T.ocr_image(b, ud(ctx).get("ocrlang", OCR_LANGS)) for _, b in pages)
        ud(ctx)["last_text"] = text
        await send_long(update, text or "(لا يوجد نص)", "📄 نص الملف")
        return

    if mode == "pages":
        imgs = T.pdf_pages_to_images(data)
        await _send_images(update, ctx, imgs, "صفحة")
        return

    msg = await update.message.reply_text("⏳ جاري استخراج الصور…")
    imgs = T.pdf_extract_images(data)
    if not imgs:
        await msg.edit_text("لم أجد صوراً مضمّنة — سأحوّل الصفحات إلى صور 🖼")
        imgs = T.pdf_pages_to_images(data)
    else:
        await msg.edit_text(f"✅ وجدت {len(imgs)} صورة، جاري الإرسال…")

    if mode == "zip":
        zip_bytes = T.make_zip(imgs)
        bio = io.BytesIO(zip_bytes)
        bio.name = "images.zip"
        await update.message.reply_document(bio, caption=f"🗜 {len(imgs)} صورة")
        return

    ud(ctx)["last_images"] = [b for _, b in imgs]
    await _send_images(update, ctx, imgs, "صورة")


async def _send_images(update: Update, ctx, imgs, label: str):
    ocr_all = []
    batch = []
    for i, (name, data) in enumerate(imgs, 1):
        batch.append(InputMediaPhoto(io.BytesIO(data), caption=f"{label} {i} — {name}"))
        if len(batch) == 10:
            await _safe_group(update, batch)
            batch = []
    if batch:
        await _safe_group(update, batch)

    if ud(ctx).get("auto_ocr", True):
        for _, data in imgs[:15]:
            t = T.ocr_image(data, ud(ctx).get("ocrlang", OCR_LANGS))
            if t:
                ocr_all.append(t)
        if ocr_all:
            joined = "\n\n---\n\n".join(ocr_all)
            ud(ctx)["last_text"] = joined
            await send_long(update, joined, "🔤 النص المستخرج من الصور")


async def _safe_group(update: Update, batch):
    try:
        await update.message.reply_media_group(batch)
    except Exception:
        for m in batch:
            try:
                await update.message.reply_photo(m.media, caption=m.caption)
            except Exception:
                pass
    await asyncio.sleep(0.4)


async def cmd_split(update: Update, ctx):
    data = ud(ctx).get("last_pdf")
    if not data:
        await update.message.reply_text("أرسل ملف PDF أولاً.")
        return
    try:
        a, b = int(ctx.args[0]), int(ctx.args[1])
    except Exception:
        await update.message.reply_text("الاستعمال: /split 1 5")
        return
    out = io.BytesIO(T.pdf_split(data, a, b))
    out.name = f"split_{a}_{b}.pdf"
    await update.message.reply_document(out, caption=f"✂️ الصفحات {a}-{b}")


async def cmd_merge(update: Update, ctx):
    pdfs = ud(ctx).get("pdfs", [])
    if len(pdfs) < 2:
        await update.message.reply_text("أرسل ملفين PDF على الأقل ثم استعمل /merge")
        return
    out = io.BytesIO(T.pdf_merge(pdfs))
    out.name = "merged.pdf"
    await update.message.reply_document(out, caption=f"🔗 دمج {len(pdfs)} ملفات")


async def cmd_topdf(update: Update, ctx):
    imgs = ud(ctx).get("photos", []) or ud(ctx).get("last_images", [])
    if not imgs:
        await update.message.reply_text("أرسل صوراً أولاً.")
        return
    out = io.BytesIO(T.images_to_pdf(imgs))
    out.name = "images.pdf"
    await update.message.reply_document(out, caption=f"📕 {len(imgs)} صورة → PDF")


async def cmd_clearfiles(update: Update, ctx):
    for k in ("last_pdf", "pdfs", "photos", "last_images", "last_photo", "last_text"):
        ud(ctx).pop(k, None)
    await update.message.reply_text("🧹 تم تفريغ الملفات المؤقتة.")


# ---------------- الصور و OCR ----------------
async def on_photo(update: Update, ctx):
    if not await guard(update):
        return
    ph = update.message.photo[-1] if update.message.photo else None
    f = await (ph.get_file() if ph else update.message.document.get_file())
    data = bytes(await f.download_as_bytearray())
    ud(ctx)["last_photo"] = data
    ud(ctx).setdefault("photos", []).append(data)
    st.bump_jobs(update.effective_user.id)

    await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    text = T.ocr_image(data, ud(ctx).get("ocrlang", OCR_LANGS))
    if not text:
        await update.message.reply_text("❌ لم أتمكن من قراءة نص في هذه الصورة.")
        return
    ud(ctx)["last_text"] = text
    await send_long(update, text, "🔤 النص المستخرج")
    pair = ud(ctx).get("pair")
    if pair:
        tr, n = st.translate_with_glossary(text, pair)
        if n:
            await send_long(update, tr, f"🌐 ترجمة ({pair})")


async def cmd_ocrlang(update: Update, ctx):
    if not ctx.args:
        await update.message.reply_text(f"اللغات الحالية: {ud(ctx).get('ocrlang', OCR_LANGS)}")
        return
    ud(ctx)["ocrlang"] = ctx.args[0]
    await update.message.reply_text(f"✅ لغات OCR: {ctx.args[0]}")


async def cmd_img(update: Update, ctx):
    data = ud(ctx).get("last_photo")
    if not data:
        await update.message.reply_text("أرسل صورة أولاً.")
        return
    op = (ctx.args[0] if ctx.args else "").lower()
    val = ctx.args[1] if len(ctx.args) > 1 else ""
    if op not in {"gray", "rotate", "resize", "compress", "invert", "enhance"}:
        await update.message.reply_text("الاستعمال: /img gray|rotate 90|resize 800|compress|invert|enhance")
        return
    out, ext = T.image_transform(data, op, val)
    bio = io.BytesIO(out)
    bio.name = f"{op}.{ext}"
    await update.message.reply_document(bio, caption=f"✅ {op}")


async def cmd_imginfo(update: Update, ctx):
    data = ud(ctx).get("last_photo")
    if not data:
        await update.message.reply_text("أرسل صورة أولاً.")
        return
    await update.message.reply_text(T.image_info(data))


# ---------------- الترجمة بالقاموس ----------------
async def cmd_pair(update: Update, ctx):
    if not ctx.args:
        await update.message.reply_text("الاستعمال: /pair ar->en")
        return
    pair = ctx.args[0]
    ud(ctx)["pair"] = pair
    await update.message.reply_text(
        f"✅ زوج الترجمة: <code>{pair}</code> — عدد المدخلات: {st.glossary_size(pair)}",
        parse_mode=ParseMode.HTML,
    )


async def cmd_pairs(update: Update, ctx):
    ps = st.glossary_pairs()
    if not ps:
        await update.message.reply_text("لا يوجد قاموس بعد. على الأدمن استعمال /teach")
        return
    lines = [f"• <code>{p}</code> — {st.glossary_size(p)} مدخل" for p in ps]
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_tr(update: Update, ctx):
    pair = ud(ctx).get("pair")
    if not pair:
        await update.message.reply_text("اختر زوج اللغة أولاً: /pair ar->en")
        return
    text = " ".join(ctx.args) or (
        update.message.reply_to_message.text if update.message.reply_to_message else ""
    )
    if not text:
        await update.message.reply_text("اكتب النص بعد الأمر: /tr مرحبا")
        return
    out, n = st.translate_with_glossary(text, pair)
    await send_long(update, out, f"🌐 ترجمة ({pair}) — {n} استبدال")


async def cmd_trlast(update: Update, ctx):
    pair = ud(ctx).get("pair")
    text = ud(ctx).get("last_text")
    if not pair or not text:
        await update.message.reply_text("تحتاج /pair ونصاً مُستخرجاً سابقاً.")
        return
    out, n = st.translate_with_glossary(text, pair)
    await send_long(update, out, f"🌐 ترجمة ({pair}) — {n} استبدال")


async def cmd_dict(update: Update, ctx):
    pair = ud(ctx).get("pair")
    if not pair or not ctx.args:
        await update.message.reply_text("الاستعمال: /pair ar->en ثم /dict كلمة")
        return
    q = " ".join(ctx.args).lower()
    table = st.load_glossary().get(pair, {})
    hits = [f"• {k} → {v}" for k, v in table.items() if q in k.lower() or q in v.lower()][:30]
    await update.message.reply_text("\n".join(hits) if hits else "لا توجد نتائج.")


# ---------------- أدوات النص ----------------
def _arg_or_last(ctx, update) -> str:
    t = " ".join(ctx.args)
    if not t and update.message.reply_to_message:
        t = update.message.reply_to_message.text or ""
    return t or ud(ctx).get("last_text", "")


async def cmd_stats(update: Update, ctx):
    t = _arg_or_last(ctx, update)
    await update.message.reply_text(T.text_stats(t) if t else "لا يوجد نص.")


async def cmd_sum(update: Update, ctx):
    t = _arg_or_last(ctx, update)
    await send_long(update, T.summarize(t), "🧠 ملخص") if t else await update.message.reply_text("لا يوجد نص.")


async def cmd_keys(update: Update, ctx):
    t = _arg_or_last(ctx, update)
    if not t:
        await update.message.reply_text("لا يوجد نص.")
        return
    await update.message.reply_text("🔑 " + "، ".join(T.keywords(t)))


async def cmd_clean(update: Update, ctx):
    t = _arg_or_last(ctx, update)
    if not t:
        await update.message.reply_text("لا يوجد نص.")
        return
    out = T.clean_text(t)
    ud(ctx)["last_text"] = out
    await send_long(update, out, "🧼 نص منظّف")


async def cmd_txt(update: Update, ctx):
    t = ud(ctx).get("last_text")
    if not t:
        await update.message.reply_text("لا يوجد نص محفوظ.")
        return
    bio = io.BytesIO(t.encode("utf-8"))
    bio.name = "text.txt"
    await update.message.reply_document(bio)


async def cmd_txtpdf(update: Update, ctx):
    t = ud(ctx).get("last_text")
    if not t:
        await update.message.reply_text("لا يوجد نص محفوظ.")
        return
    bio = io.BytesIO(T.text_to_pdf(t))
    bio.name = "text.pdf"
    await update.message.reply_document(bio)


async def cmd_qr(update: Update, ctx):
    t = " ".join(ctx.args) or ud(ctx).get("last_text", "")[:1000]
    if not t:
        await update.message.reply_text("اكتب نصاً: /qr مرحبا")
        return
    img = qrcode.make(t)
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    bio.name = "qr.png"
    await update.message.reply_photo(bio, caption="🔳 رمز QR")


async def cmd_note(update: Update, ctx):
    raw = " ".join(ctx.args)
    if "|" not in raw:
        await update.message.reply_text("الاستعمال: /note العنوان | المحتوى")
        return
    title, content = [x.strip() for x in raw.split("|", 1)]
    nid = st.add_note(update.effective_user.id, title, content)
    await update.message.reply_text(f"💾 حُفظت الملاحظة #{nid}")


async def cmd_notes(update: Update, ctx):
    rows = st.list_notes(update.effective_user.id)
    if not rows:
        await update.message.reply_text("لا توجد ملاحظات.")
        return
    await update.message.reply_text(
        "\n".join(f"#{r['id']} — {r['title']} ({r['created']})" for r in rows)
    )


async def cmd_getnote(update: Update, ctx):
    try:
        r = st.get_note(update.effective_user.id, int(ctx.args[0]))
    except Exception:
        r = None
    await update.message.reply_text(f"📝 {r['title']}\n\n{r['content']}" if r else "غير موجودة.")


async def cmd_delnote(update: Update, ctx):
    try:
        ok = st.delete_note(update.effective_user.id, int(ctx.args[0]))
    except Exception:
        ok = False
    await update.message.reply_text("🗑 حُذفت." if ok else "غير موجودة.")


# ---------------- أوامر الأدمن ----------------
def _decode(data: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "cp1256", "latin-1"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode("utf-8", "ignore")


async def _absorb_glossary(update: Update, ctx, text: str):
    pair = ud(ctx).pop("teach_pair")
    entries = st.parse_glossary_text(text)
    if not entries:
        await update.message.reply_text(
            "⚠️ لم أجد مدخلات صالحة.\nالصيغة المطلوبة سطراً بسطر:\n<code>كلمة = translation</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    total = st.add_entries(pair, entries)
    await update.message.reply_text(
        f"📚 تم تلقين <b>{len(entries)}</b> مدخلاً للزوج <code>{pair}</code>.\n"
        f"إجمالي القاموس: {total}",
        parse_mode=ParseMode.HTML,
    )


async def cmd_teach(update: Update, ctx):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("👑 هذا الأمر للأدمن فقط.")
    if not ctx.args:
        return await update.message.reply_text("الاستعمال: /teach ar->en ثم أرسل ملف القاموس")
    ud(ctx)["teach_pair"] = ctx.args[0]
    await update.message.reply_text(
        f"📥 أرسل الآن ملف الكتاب/القاموس (.txt) أو الصقه كنص للزوج <code>{ctx.args[0]}</code>.\n"
        "كل سطر: <code>الكلمة = الترجمة</code>",
        parse_mode=ParseMode.HTML,
    )


async def cmd_teachtext(update: Update, ctx):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("👑 هذا الأمر للأدمن فقط.")
    raw = update.message.text.split("\n", 1)
    head = raw[0].split()
    if len(head) < 2 or len(raw) < 2:
        return await update.message.reply_text("الاستعمال:\n/teachtext ar->en\nكلمة = word")
    ud(ctx)["teach_pair"] = head[1]
    await _absorb_glossary(update, ctx, raw[1])


async def cmd_delpair(update: Update, ctx):
    if not is_admin(update.effective_user.id):
        return
    ok = st.delete_pair(ctx.args[0]) if ctx.args else False
    await update.message.reply_text("🗑 حُذف الزوج." if ok else "غير موجود.")


async def cmd_exportdict(update: Update, ctx):
    if not is_admin(update.effective_user.id):
        return
    pair = ctx.args[0] if ctx.args else ""
    table = st.load_glossary().get(pair, {})
    if not table:
        return await update.message.reply_text("لا يوجد قاموس بهذا الزوج.")
    body = "\n".join(f"{k} = {v}" for k, v in table.items())
    bio = io.BytesIO(body.encode("utf-8"))
    bio.name = f"{pair.replace('->','_')}.txt"
    await update.message.reply_document(bio, caption=f"📚 {len(table)} مدخل")


async def cmd_broadcast(update: Update, ctx):
    if not is_admin(update.effective_user.id):
        return
    msg = " ".join(ctx.args)
    if not msg:
        return await update.message.reply_text("الاستعمال: /broadcast رسالتك")
    ok = 0
    for uid in st.all_user_ids():
        try:
            await ctx.bot.send_message(uid, f"📢 {msg}")
            ok += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await update.message.reply_text(f"✅ أُرسلت إلى {ok} مستخدم.")


async def cmd_ban(update: Update, ctx):
    if not is_admin(update.effective_user.id):
        return
    st.set_banned(int(ctx.args[0]), True)
    await update.message.reply_text("🚫 تم الحظر.")


async def cmd_unban(update: Update, ctx):
    if not is_admin(update.effective_user.id):
        return
    st.set_banned(int(ctx.args[0]), False)
    await update.message.reply_text("✅ تم رفع الحظر.")


async def cmd_admin(update: Update, ctx):
    if not is_admin(update.effective_user.id):
        return
    s = st.stats()
    up = int(time.time() - START_TIME)
    await update.message.reply_text(
        f"👑 لوحة الأدمن\n👥 مستخدمون: {s['users']}\n⚙️ عمليات: {s['jobs']}\n"
        f"📝 ملاحظات: {s['notes']}\n📚 أزواج القاموس: {len(st.glossary_pairs())}\n"
        f"⏱ التشغيل: {up//3600}س {(up%3600)//60}د"
    )


# ---------------- نص عادي ----------------
async def on_text(update: Update, ctx):
    if not await guard(update):
        return
    text = update.message.text or ""
    if is_admin(update.effective_user.id) and ud(ctx).get("teach_pair"):
        return await _absorb_glossary(update, ctx, text)
    ud(ctx)["last_text"] = text
    pair = ud(ctx).get("pair")
    if pair:
        out, n = st.translate_with_glossary(text, pair)
        if n:
            return await send_long(update, out, f"🌐 ترجمة ({pair})")
    await update.message.reply_text(
        "📌 حُفظ النص. جرّب /sum أو /stats أو /keys أو /tr — و /help للمزيد."
    )


async def on_error(update, ctx):
    log.exception("Error", exc_info=ctx.error)
    try:
        if isinstance(update, Update) and update.message:
            await update.message.reply_text("⚠️ حدث خطأ أثناء المعالجة. حاول مجدداً.")
    except Exception:
        pass


def main():
    if not BOT_TOKEN:
        raise SystemExit("❌ ضع BOT_TOKEN في config.py أو في متغيرات البيئة.")
    st.init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    cmds = {
        "start": cmd_start, "help": cmd_help, "id": cmd_id, "ping": cmd_ping, "about": cmd_about,
        "pdfmode": cmd_pdfmode, "split": cmd_split, "merge": cmd_merge, "topdf": cmd_topdf,
        "clearfiles": cmd_clearfiles, "ocrlang": cmd_ocrlang, "img": cmd_img, "imginfo": cmd_imginfo,
        "pair": cmd_pair, "pairs": cmd_pairs, "tr": cmd_tr, "trlast": cmd_trlast, "dict": cmd_dict,
        "stats": cmd_stats, "sum": cmd_sum, "keys": cmd_keys, "clean": cmd_clean, "txt": cmd_txt,
        "txtpdf": cmd_txtpdf, "qr": cmd_qr, "note": cmd_note, "notes": cmd_notes,
        "getnote": cmd_getnote, "delnote": cmd_delnote,
        "teach": cmd_teach, "teachtext": cmd_teachtext, "delpair": cmd_delpair,
        "exportdict": cmd_exportdict, "broadcast": cmd_broadcast, "ban": cmd_ban,
        "unban": cmd_unban, "admin": cmd_admin,
    }
    for name, fn in cmds.items():
        app.add_handler(CommandHandler(name, fn))

    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE, on_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)

    log.info("Bot started ✅")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
