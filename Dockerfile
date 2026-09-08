# --- Erste Stufe: Pakete bauen und installieren ---
FROM python:3.10-slim AS builder

WORKDIR /app

# Notwendige System-Tools für den Build installieren
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Pakete in ein separates Verzeichnis für die Übertragung in die nächste Stufe installieren
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Zweite Stufe: Finales und leichtes Image für die Ausführung ---
FROM python:3.10-slim

WORKDIR /app

# Nur die installierten Pakete aus der vorherigen Stufe kopieren
COPY --from=builder /install /usr/local

COPY . .

# Standard-Port der Anwendung festlegen
EXPOSE 5000

# Befehl zum Ausführen der Anwendung
CMD ["python", "app.py"]