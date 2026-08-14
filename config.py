"""إعدادات البوت — املأ التوكن وأيدي الأدمن هنا (أو عبر متغيرات البيئة)."""
import os

# ====== املأ هذين الحقلين بنفسك ======
BOT_TOKEN = os.getenv("BOT_TOKEN", "")        # ضع توكن البوت هنا
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))    # ضع أيدي الأدمن هنا (رقم)
# =====================================

# مجلد البيانات (على Render استعمل قرصاً دائماً إن أردت الحفظ)
DATA_DIR = os.getenv("DATA_DIR", "data")
DB_PATH = os.path.join(DATA_DIR, "bot.db")
GLOSSARY_PATH = os.path.join(DATA_DIR, "glossary.json")
TMP_DIR = os.path.join(DATA_DIR, "tmp")

# لغات OCR المتاحة في tesseract (تُثبّت عبر apt)
OCR_LANGS = os.getenv("OCR_LANGS", "ara+eng+fra")

# الحد الأقصى لعدد الصور المستخرجة من ملف PDF واحد
MAX_IMAGES_PER_PDF = int(os.getenv("MAX_IMAGES_PER_PDF", "100"))
# أصغر أبعاد للصورة حتى تُرسل (لتجاهل الأيقونات الصغيرة)
MIN_IMAGE_SIDE = int(os.getenv("MIN_IMAGE_SIDE", "60"))

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(TMP_DIR, exist_ok=True)
