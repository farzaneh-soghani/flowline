import polib
from deep_translator import GoogleTranslator
import os

# Sprachen, die automatisch übersetzt werden sollen 
LANGUAGES = ["en", "fa", "ru", "pl", "uk", "es", "fr", "zh", "ja", "tr"]

for lang in LANGUAGES:
    po_file_path = f"translations/{lang}/LC_MESSAGES/messages.po"

    if not os.path.exists(po_file_path):
        print(f"⚠️ Datei für die Sprache {lang} nicht gefunden. Bitte zuerst pybabel"
        " init ausführen.")
        continue

    po = polib.pofile(po_file_path)
    translator = GoogleTranslator(source="de", target=lang)

    print(f"🔄 In Bearbeitung der automatischen Übersetzung für die Sprache: {lang} ...")

    translated_count = 0
    for entry in po:
        # falls der Text noch nicht übersetzt wurde
        if not entry.msgstr and entry.msgid:
            try:
                entry.msgstr = translator.translate(entry.msgid)
                translated_count += 1
            except Exception as e:
                print(f"❌ Fehler bei der Übersetzung '{entry.msgid}': {e}")

    po.save()
    print(f"✅ {translated_count} Übersetzungen für die Sprache {lang} erfolgreich durchgeführt!")

print("\n🎉 Alle Übersetzungen sind abgeschlossen! Führen Sie nun den folgenden Befehl aus:")
print("pybabel compile -d translations")
