import os
import re

TEMPLATES_DIR = "templates"


def clean_and_fix_html():
    if not os.path.exists(TEMPLATES_DIR):
        print(f"❌ پوشه {TEMPLATES_DIR} پیدا نشد!")
        return

    count = 0
    for root, _, files in os.walk(TEMPLATES_DIR):
        for file in files:
            if file.endswith(".html"):
                file_path = os.path.join(root, file)

                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # 1. پاک‌سازی تمام اسلش‌های اشتباه مثل (\')
                new_content = content.replace(r"\'", "'").replace(r"\"", '"')

                # 2. الگوی منظم درست برای placeholder و title بدون تولید اسلش
                new_content = re.sub(
                    r'placeholder="(?!\{\{\s*_\()(.*?)"',
                    r'placeholder="{{ _(\1) }}"',
                    new_content,
                )
                new_content = re.sub(
                    r'title="(?!\{\{\s*_\()(.*?)"', r'title="{{ _(\1) }}"', new_content
                )

                if new_content != content:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    print(f"✅ فایل اصلاح و پاک‌سازی شد: {file_path}")
                    count += 1

    print(f"\n🎉 با موفقیت {count} فایل اصلاح شد!")


if __name__ == "__main__":
    clean_and_fix_html()
