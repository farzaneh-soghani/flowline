# استفاده از ایمیج رسمی و سبک پایتون
FROM python:3.10-slim

# تعیین پوشه کاری داخل کانتینر
WORKDIR /app

# نصب ابزارهای پایه‌ای سیستم‌عامل در صورت نیاز
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# کپی کردن فایل نیازمندی‌ها به داخل کانتینر
COPY requirements.txt .

# نصب پکیج‌های پایتون
RUN pip install --no-cache-dir -r requirements.txt

# کپی کردن بقیه فایل‌های پروژه به داخل کانتینر
COPY . .

# تعیین پورت پیش‌فرض اپلیکیشن
EXPOSE 5000

# دستور نهایی برای اجرای اپلیکیشن (با استفاده از Gunicorn یا Flask run)
CMD ["python", "app.py"]