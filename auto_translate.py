import polib
from deep_translator import GoogleTranslator
import os

# زبان‌هایی که می‌خواهید خودکار ترجمه شوند
LANGUAGES = ['fa', 'en', 'ar', 'tr']

for lang in LANGUAGES:
    po_file_path = f'translations/{lang}/LC_MESSAGES/messages.po'
    
    if not os.path.exists(po_file_path):
        print(f"⚠️ فایل برای زبان {lang} یافت نشد. ابتدا pybabel init را بزنید.")
        continue

    po = polib.pofile(po_file_path)
    translator = GoogleTranslator(source='de', target=lang)
    
    print(f"🔄 در حال ترجمه خودکار به زبان: {lang} ...")
    
    translated_count = 0
    for entry in po:
        # اگر متن هنوز ترجمه نشده باشد
        if not entry.msgstr and entry.msgid:
            try:
                entry.msgstr = translator.translate(entry.msgid)
                translated_count += 1
            except Exception as e:
                print(f"❌ خطا در ترجمه '{entry.msgid}': {e}")
    
    po.save()
    print(f"✅ {translated_count} عبارت برای زبان {lang} با موفقیت ترجمه شد!")

print("\n🎉 تمام ترجمه‌ها انجام شدند! حالا دستور زیر را اجرا کنید:")
print("pybabel compile -d translations")