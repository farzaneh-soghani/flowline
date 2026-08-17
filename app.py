import os
from dotenv import load_dotenv

# Lade Umgebungsvariablen aus der .env-Datei
load_dotenv()

import io
from datetime import datetime, timedelta
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file,
    session,
    current_app,
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer
from flask_mail import Mail, Message
from flask_babel import Babel, gettext as _

# Imports für die PDF-Generierung
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# --- KONFIGURATION DER ANWENDUNG ---
# Initialisierung der Flask-Anwendung
app = Flask(__name__)

# Sicherer Secret-Key für Session-Management und Tokens (wird aus .env geladen oder zufällig generiert)
app.secret_key = os.getenv("SECRET_KEY") or os.urandom(24)

# Datenbank-URL Konfiguration (Unterstützung für PostgreSQL auf Render und SQLite lokal)
db_url = os.getenv("DATABASE_URL", "sqlite:///flowline.db")
if db_url.startswith("postgres://"):  # pragma: no cover
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# --- MAIL-KONFIGURATION (SICHER) ---
# Konfiguration des E-Mail-Servers (Laden von Umgebungswerten für maximale Sicherheit)
app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", 587))
# Umwandlung des String-Wertes ('True'/'False') in einen booleschen Wert
app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "True") == "True"
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
# Definition des Standard-Absenders mit Anzeigenamen und Haupt-E-Mail
app.config["MAIL_DEFAULT_SENDER"] = ("FlowLine Support", os.getenv("MAIL_USERNAME"))

# Initialisierung der Mail- und Datenbank-Erweiterungen für die Anwendung
mail = Mail(app)
db = SQLAlchemy(app)

# --- LOGIN MANAGER ---
# Initialisiert den Login-Manager und bindet ihn an die Flask-Anwendung
login_manager = LoginManager()
login_manager.init_app(app)

# Definiert die Route für die Login-Seite, falls der Zugriff auf geschützte Seiten verweigert wird
login_manager.login_view = "login"

# Deaktiviert die Standard-Flash-Nachricht bei nicht autorisiertem Zugriff
login_manager.login_message = None


# --- HELPER FUNCTIONS FOR PASSWORD RESET ---
def generate_reset_token(user):
    # Generiert ein sicheres, zeitlich begrenztes Token für die Passwortwiederherstellung
    serializer = URLSafeTimedSerializer(app.secret_key)
    return serializer.dumps(
        {"email": user.email, "hash": user.password_hash}, salt="password-reset-salt"
    )


def verify_reset_token(token, expiration=3600):
    # Überprüft die Gültigkeit des Tokens und verifiziert den Benutzer anhand der gespeicherten Daten
    serializer = URLSafeTimedSerializer(app.secret_key)
    try:
        # Dekodiert das Token und prüft das Ablaufdatum (Standard: 3600 Sekunden / 1 Stunde)
        data = serializer.loads(token, salt="password-reset-salt", max_age=expiration)
        email = data.get("email")
        token_hash = data.get("hash")

        user = User.query.filter_by(email=email).first()
        # Gibt None zurück, wenn der Benutzer nicht existiert oder sich das Passwort zwischenzeitlich geändert hat
        if not user or user.password_hash != token_hash:
            return None

        return user
    except Exception:
        # Fängt Fehler ab (z. B. abgelaufenes oder manipuliertes Token) und gibt None zurück
        return None


# --- BABEL LOCALE SELECTOR ---
def get_locale():
    # Überprüft, ob der Benutzer bereits eine Sprache in der Session ausgewählt hat
    if "lang" in session:
        return session["lang"]
    # Ermittelt die beste Übereinstimmung aus den akzeptierten Browsersprachen oder fällt auf 'de' (Deutsch) zurück
    return (
        request.accept_languages.best_match(
            ["de", "en", "fa", "ar", "tr", "ru", "pl", "uk", "es", "fr", "zh", "ja"]
        )
        or "de"
    )


# Initialisierung von Flask-Babel mit der benutzerdefinierten Funktion zur Sprachauswahl
babel = Babel(app, locale_selector=get_locale)


# --- DATENBANK-MODELLE ---
class User(UserMixin, db.Model):
    # Eindeutige ID für jeden Benutzer (Primärschlüssel)
    id = db.Column(db.Integer, primary_key=True)

    # E-Mail-Adresse des Benutzers (muss eindeutig sein und darf nicht leer sein)
    email = db.Column(db.String(120), unique=True, nullable=False)

    # Gespeicherter Passwort-Hash (sichere Speicherung statt Klartext)
    password_hash = db.Column(db.String(200), nullable=False)

    # Verknüpfung zu den Stellenbewerbungen (Eins-zu-viele-Beziehung)
    jobs = db.relationship("Job", backref="owner", lazy=True)

    def set_password(self, password):
        # Generiert einen sicheren Passwort-Hash mit der scrypt-Methode
        self.password_hash = generate_password_hash(password, method="scrypt")

    def check_password(self, password):
        # Überprüft, ob das eingegebene Passwort mit dem gespeicherten Hash übereinstimmt
        return check_password_hash(self.password_hash, password)


# --- JOB MODEL ---
class Job(db.Model):
    # Eindeutige ID für jeden Bewerbungseintrag (Primärschlüssel)
    id = db.Column(db.Integer, primary_key=True)

    # Name des Unternehmens und die angestrebte Position (Pflichtfelder)
    firma = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(100), nullable=False)

    # Aktueller Status der Bewerbung (z. B. "Eingereicht", "Absage", "Zusage")
    status = db.Column(db.String(50), nullable=False)

    # Bewerbungsdatum (Standardmäßig das aktuelle Datum im Format YYYY-MM-DD)
    datum = db.Column(
        db.String(20), default=lambda: datetime.now().strftime("%Y-%m-%d")
    )

    # Optionales Datum für eine Nachverfolgung (Follow-up)
    follow_up_datum = db.Column(db.String(20), nullable=True)

    # Status, ob bereits nachgefasst wurde (Standard: False)
    nachgefasst = db.Column(db.Boolean, default=False)

    # Zusätzliche Notizen zur Bewerbung
    notes = db.Column(db.Text, default="")

    # Fremdschlüssel zur Verknüpfung des Eintrags mit dem entsprechenden Benutzer
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


# --- USER LOADER & DATENBANK-INITIALISIERUNG ---
@login_manager.user_loader
def load_user(user_id):
    # Lädt den Benutzer anhand der gespeicherten Session-ID aus der Datenbank
    return db.session.get(User, int(user_id))


# Erstellt alle definierten Datenbanktabellen beim Anwendungsstart, falls sie noch nicht existieren
with app.app_context():
    try:
        db.create_all()
    except Exception as e:  # pragma: no cover
        print(f"Fehler beim Erstellen der Tabellen: {e}")


# --- JINJA FILTER FÜR DEUTSCHES DATUMSFORMAT ---
@app.template_filter("german_date")
def german_date_filter(date_str):
    # Gibt 'k.A.' (keine Angabe) zurück, wenn kein Datum angegeben ist (unterstützt Mehrsprachigkeit)
    if not date_str:
        return _("k.A.")

    try:
        # Konvertiert den String vom ISO-Format (YYYY-MM-DD) in ein Datetime-Objekt
        dt = datetime.strptime(str(date_str), "%Y-%m-%d")
        # Formatiert das Datum in das deutsche Format (DD.MM.YYYY)
        return dt.strftime("%d.%m.%Y")
    except ValueError:
        # Falls das Format nicht übereinstimmt, wird der ursprüngliche String zurückgegeben
        return str(date_str)


# --- AUTHENTIFIZIERUNG: REGISTRIERUNG ---
@app.route("/register", methods=["GET", "POST"])
def register():
    # Verarbeitet die Formulareingaben beim Absenden (POST-Anfrage)
    if request.method == "POST":
        # Erfasst E-Mail und Passwort aus dem Formular (E-Mail wird bereinigt und klein geschrieben)
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        # Validierung: Prüft, ob Pflichtfelder ausgefüllt sind
        if not email or not password:
            flash(_("❌ Bitte E-Mail und Passwort eingeben!"))
            return redirect(url_for("register"))

        # Validierung: Prüft die Mindestlänge des Passworts (mind. 8 Zeichen)
        if len(password) < 8:
            flash(_("❌ Das Passwort muss mindestens 8 Zeichen lang sein!"))
            return redirect(url_for("register"))

        # Validierung: Prüft, ob die E-Mail-Adresse bereits in der Datenbank existiert
        if User.query.filter_by(email=email).first():
            flash(_("❌ Diese E-Mail-Adresse ist bereits registriert!"))
            return redirect(url_for("register"))

        # Erstellt den neuen Benutzer und speichert ihn in der Datenbank
        try:
            new_user = User(email=email)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for("login"))
        except Exception:
            # Roolback bei Datenbankfehlern zur Vermeidung von Fehlzuständen
            db.session.rollback()
            flash(_("❌ Registrierung fehlgeschlagen."))
            return redirect(url_for("register"))

    # Zeigt das Registrierungsformular bei einer GET-Anfrage an
    return render_template("register.html")


# --- AUTHENTIFIZIERUNG: LOGIN ---
@app.route("/login", methods=["GET", "POST"])
def login():
    # Verarbeitet die Anmeldedaten beim Absenden des Formulars (POST-Anfrage)
    if request.method == "POST":
        # Liest E-Mail und Passwort aus dem Formular aus
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        # Sucht den Benutzer anhand der E-Mail-Adresse in der Datenbank
        user = User.query.filter_by(email=email).first()

        # Überprüft, ob der Benutzer existiert und das Passwort korrekt ist
        if user and user.check_password(password):
            # Meldet den Benutzer an und startet die Sitzung (Session)
            login_user(user)
            return redirect(url_for("index"))
        else:
            # Zeigt eine Fehlermeldung bei falschen Anmeldedaten an
            flash(_("❌ Ungültige E-Mail-Adresse oder Passwort!"))

    # Zeigt das Anmeldeformular bei einer GET-Anfrage an
    return render_template("login.html")


# --- AUTHENTIFIZIERUNG: LOGOUT ---
@app.route("/logout")
@login_required
def logout():
    # Meldet den aktuell angemeldeten Benutzer ab und beendet die Sitzung
    logout_user()

    # Leitet den Benutzer nach dem Logout zur Login-Seite weiter
    return redirect(url_for("login"))


# --- PASSWORT-WIEDERHERSTELLUNG: ANFRAGE ---
@app.route("/reset_password_request", methods=["GET", "POST"])
def reset_password_request():
    # Verarbeitet die Anfrage zur Passwortwiederherstellung (POST-Anfrage)
    if request.method == "POST":
        # Erfasst die E-Mail-Adresse aus dem Formular
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()

        # Überprüft, ob der Benutzer in der Datenbank existiert
        if user:
            # Generiert ein sicheres Token für den Wiederherstellungs-Link
            token = generate_reset_token(user)
            reset_url = url_for("reset_password", token=token, _external=True)

            # Übersetzbarer Betreff und E-Mail-Text
            subject_text = _("Passwort zurücksetzen - FlowLine")
            body_text = _(
                "Hallo,\n\n"
                "Sie haben eine Anfrage zum Zurücksetzen Ihres Passworts für FlowLine gestellt.\n"
                "Klicken Sie auf den folgenden Link, um ein neues Passwort zu vergeben:\n\n"
                "%(url)s\n\n"
                "Dieser Link ist 1 Stunde lang gültig.\n"
                "Wenn Sie diese Anfrage nicht gestellt haben, "
                "können Sie diese E-Mail einfach ignorieren.\n\n"
                "Viele Grüße\n"
                "Ihr FlowLine Team"
            ) % {"url": reset_url}

            # Erstellt die E-Mail-Nachricht
            msg = Message(subject_text, recipients=[user.email])
            msg.body = body_text

            # Versuch, die E-Mail über den Flask-Mail-Dienst zu versenden
            try:
                mail.send(msg)
                flash(
                    _(
                        "Ein Link zum Zurücksetzen des Passworts wurde an Ihre E-Mail gesendet."
                    )
                )
            except Exception as e:  # pragma: no cover
                # Falls wir uns in einer Testumgebung befinden, poste Fehler, damit wir ihn verstehen können.
                if current_app.config.get("TESTING"):
                    raise e

                print(f"Fehler beim E-Mail-Versand: {e}")
                flash(
                    _(
                        "❌ Fehler beim Senden der E-Mail. Bitte versuchen Sie es später erneut."
                    )
                )

            return redirect(url_for("login"))
        else:
            # Fehlermeldung, wenn die E-Mail-Adresse nicht gefunden wurde
            flash(_("❌ Diese E-Mail-Adresse wurde nicht gefunden."))

    # Zeigt das Formular zur Anforderung des Passwort-Resets an
    return render_template("reset_request.html")


# --- PASSWORT-WIEDERHERSTELLUNG: PASSWORT ÄNDERN ---
@app.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    # Überprüft die Gültigkeit und das Ablaufdatum des gesendeten Tokens
    user = verify_reset_token(token)
    if not user:
        flash(_("❌ Der Link ist ungültig, abgelaufen oder wurde bereits verwendet."))
        return redirect(url_for("reset_password_request"))

    # Verarbeitet das Formular zur Passworteingabe (POST-Anfrage)
    if request.method == "POST":
        password = request.form.get("password", "")

        # Validierung: Prüft die Mindestlänge des neuen Passworts (mind. 8 Zeichen)
        if len(password) < 8:
            flash(_("❌ Das Passwort muss mindestens 8 Zeichen lang sein!"))
            return redirect(url_for("reset_password", token=token))

        # Speichert das neue Passwort sicher als Hash in der Datenbank
        try:
            user.set_password(password)
            db.session.commit()
            flash(
                _("✅ Passwort erfolgreich geändert! Sie können sich jetzt einloggen.")
            )
            return redirect(url_for("login"))
        except Exception:
            # Rollback bei Fehlern während des Speichervorgangs
            db.session.rollback()
            flash(_("❌ Fehler beim Speichern des Passworts."))

    # Zeigt das Formular zur Vergabe des neuen Passworts an
    return render_template("reset_password.html", token=token)


# --- HAUPTSEITE UND JOB-VERWALTUNG ---
@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    # Standardmäßiges Follow-up-Datum auf 14 Tage ab heute festlegen
    default_follow_up = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")

    # Verarbeitet das Hinzufügen einer neuen Bewerbung (POST-Anfrage)
    if request.method == "POST":
        firma = request.form.get("firma", "").strip()
        position = request.form.get("position", "").strip()
        status = request.form.get("status", "offen").strip()
        custom_follow_up = request.form.get("follow_up_datum", "").strip()

        # Falls kein individuelles Datum angegeben wurde, Standardwert nutzen
        if not custom_follow_up:
            custom_follow_up = default_follow_up

        # Validierung der Pflichtfelder (Firma und Position)
        if not firma or not position:
            flash(_("❌ Firma und Position sind Pflichtfelder!"))
            return redirect(url_for("index"))

        # Neuen Job-Eintrag für den aktuellen Benutzer in der Datenbank speichern
        try:
            new_job = Job(
                firma=firma,
                position=position,
                status=status,
                follow_up_datum=custom_follow_up,
                user_id=current_user.id,
                nachgefasst=False,
            )
            db.session.add(new_job)
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash(_("❌ Fehler beim Speichern!"))

        return redirect(url_for("index"))

    # Erfasst den Suchbegriff aus den URL-Parametern (GET-Anfrage)
    search_query = request.args.get("q", "").strip()

    # Filtert die Bewerbungen des aktuell angemeldeten Benutzers
    query = Job.query.filter_by(user_id=current_user.id)
    if search_query:
        query = query.filter(
            (Job.firma.ilike(f"%{search_query}%"))
            | (Job.position.ilike(f"%{search_query}%"))
            | (Job.status.ilike(f"%{search_query}%"))
        )
    jobs = query.all()

    # Prüfung auf fällige Nachfassaktionen (Erinnerungen)
    heute = datetime.now().strftime("%Y-%m-%d")
    erinnerungen_anzahl = 0
    active_statuses = ["offen", "einladung"]

    for job in jobs:
        if (
            job.follow_up_datum
            and job.follow_up_datum <= heute
            and job.status.lower() in active_statuses
            and not job.nachgefasst
        ):

            job.is_due = True
            erinnerungen_anzahl += 1
        else:
            job.is_due = False

    # Benachrichtigung ausgeben, falls fällige Erinnerungen vorliegen
    if erinnerungen_anzahl > 0 and not search_query:
        flash(
            _(
                "Achtung: Bei %(num)d Bewerbung(en) ist ein Nachfassen oder Termin fällig!"
            )
            % {"num": erinnerungen_anzahl}
        )

    return render_template(
        "index.html",
        jobs=jobs,
        user=current_user,
        search_query=search_query,
        default_follow_up=default_follow_up,
    )


# --- JOB-VERWALTUNG: NACHGEFASST-STATUS UMSCHALTEN ---
@app.route("/toggle_nachgefasst/<int:job_id>")
@login_required
def toggle_nachgefasst(job_id):
    # Sucht den Job anhand der ID und stellt sicher, dass er dem aktuellen Benutzer gehört (404 falls nicht)
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()

    # Kehrt den aktuellen Status der Nachverfolgung um (True -> False / False -> True)
    job.nachgefasst = not job.nachgefasst

    # Speichert die Änderung in der Datenbank
    db.session.commit()

    # Leitet den Benutzer zur vorherigen Seite oder zur Hauptseite zurück
    return redirect(request.referrer or url_for("index"))


# --- GLOBAL CONTEXT PROCESSOR FÜR TEMPLATES ---
@app.context_processor
def inject_global_vars():
    # Ermittelt die aktuell gewählte Sprache für die Benutzeroberfläche
    lang = get_locale()

    # Stellt 'current_lang' und die Übersetzungsfunktion '_' global in allen Jinja-Templates zur Verfügung
    return dict(current_lang=lang, _=_)


# --- SPRACHSTEUERUNG UND LOKALISIERUNG ---
@app.route("/set_language/<lang>")
def set_language(lang):
    # Überprüft, ob die angeforderte Sprache unterstützt wird
    if lang in ["de", "en", "fa", "ar", "tr"]:
        # Speichert die gewählte Sprache in der aktuellen Sitzung (Session)
        session["lang"] = lang

    # Leitet den Benutzer zurück zur vorherigen Seite oder zur Hauptseite
    return redirect(request.referrer or url_for("index"))


# --- PDF-EXPORT VERWALTUNG ---
@app.route("/export_pdf")
@login_required
def export_pdf():
    # Ruft alle Bewerbungen des aktuell angemeldeten Benutzers ab
    jobs = Job.query.filter_by(user_id=current_user.id).all()

    # Erstellt einen In-Memory Byte-Stream für das PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    # Formatierung des Seitentitels definieren
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleStyle", parent=styles["Heading1"], fontSize=18, spaceAfter=20
    )

    # Titel mit der E-Mail-Adresse des Benutzers zum PDF hinzufügen
    elements.append(
        Paragraph(f"{_('Bewerbungsübersicht')} - {current_user.email}", title_style)
    )
    elements.append(Spacer(1, 10))

    # Kopfzeile der Tabelle festlegen
    data = [[_("Firma"), _("Position"), _("Datum"), _("Erinnerung"), _("Status")]]
    for j in jobs:
        # Erstellungsdatum im deutschen Format (TT.MM.JJJJ) formatieren
        datum_formatted = (
            datetime.strptime(j.datum, "%Y-%m-%d").strftime("%d.%m.%Y")
            if j.datum
            else "-"
        )

        # Bedingung: Bei den Status 'Zusage' oder 'Absage' wird kein Erinnungsdatum benötigt (-)
        status_lower = j.status.lower() if j.status else ""
        if status_lower in ["zusage", "absage"]:
            follow_up_formatted = "-"
        else:
            follow_up_formatted = (
                datetime.strptime(j.follow_up_datum, "%Y-%m-%d").strftime("%d.%m.%Y")
                if j.follow_up_datum
                else "-"
            )

        # Tabellenzeile hinzufügen
        data.append(
            [
                j.firma,
                j.position,
                datum_formatted,
                follow_up_formatted,
                j.status.capitalize(),
            ]
        )

    # Erstellung der Tabelle mit Spaltenbreiten und Styling
    pdf_table = Table(data, colWidths=[110, 130, 80, 90, 80])
    pdf_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 11),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f8f9fa")],
                ),
            ]
        )
    )

    elements.append(pdf_table)
    # PDF-Dokument ausführen und generieren
    doc.build(elements)

    # Stream-Zeiger an den Anfang zurücksetzen
    buffer.seek(0)

    # PDF-Datei als Download an den Benutzer senden
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Bewerbungen_{datetime.now().strftime('%Y%m%d')}.pdf",
        mimetype="application/pdf",
    )


# --- STATISTIKEN ZU DEN BEWERBUNGEN ---
@app.route("/stats")
@login_required
def stats():
    # Ruft alle Bewerbungen des aktuell angemeldeten Benutzers ab
    jobs = Job.query.filter_by(user_id=current_user.id).all()

    # Berechnet die Gesamtzahl der Bewerbungen
    total = len(jobs)

    # Ermittelt die Anzahl der offenen Bewerbungen
    offen = len([j for j in jobs if j.status.lower() == "offen"])

    # Berechnet den prozentualen Anteil der offenen Bewerbungen (Vermeidung von Division durch Null)
    offen_prozent = round((offen / total * 100), 1) if total > 0 else 0

    # Übergibt die berechneten statistischen Werte an das Template 'stats.html'
    return render_template(
        "stats.html", total=total, offen=offen, offen_prozent=offen_prozent
    )


# --- JOB-VERWALTUNG: BEWERBUNG LÖSCHEN ---
@app.route("/delete/<int:id>")
@login_required
def delete_job(id):
    # Sucht die Bewerbung anhand der ID und prüft, ob sie dem aktuellen Benutzer gehört (404 falls nicht)
    job = Job.query.filter_by(id=id, user_id=current_user.id).first_or_404()

    # Löscht den Eintrag aus der Datenbank
    try:
        db.session.delete(job)
        db.session.commit()
        flash(_("🗑️ Bewerbung gelöscht!"))
    except Exception:
        # Rollback bei Datenbankfehlern
        db.session.rollback()
        flash(_("❌ Fehler beim Löschen!"))

    # Leitet den Benutzer zurück zur Hauptseite
    return redirect(url_for("index"))


# --- JOB-VERWALTUNG: BEWERBUNG BEARBEITEN ---
@app.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_job(id):
    # Sucht die Bewerbung anhand der ID und prüft, ob sie dem aktuellen Benutzer gehört (404 falls nicht)
    job = Job.query.filter_by(id=id, user_id=current_user.id).first_or_404()

    # Verarbeitet die geänderten Daten beim Absenden des Formulars (POST-Anfrage)
    if request.method == "POST":
        firma = request.form.get("firma", "").strip()
        position = request.form.get("position", "").strip()
        status = request.form.get("status", "").strip()
        follow_up = request.form.get("follow_up_datum", "").strip()

        # Validierung: Prüft, ob Pflichtfelder ausgefüllt sind
        if not firma or not position:
            flash(_("❌ Pflichtfelder ausfüllen!"))
            return redirect(url_for("edit_job", id=id))

        # Aktualisiert die Job-Daten in der Datenbank
        try:
            job.firma = firma
            job.position = position
            job.status = status
            job.follow_up_datum = follow_up
            db.session.commit()
            return redirect(url_for("index"))
        except Exception:
            # Rollback bei Datenbankfehlern
            db.session.rollback()
            flash(_("❌ Fehler beim Aktualisieren!"))

    # Zeigt das Bearbeitungsformular bei einer GET-Anfrage an
    return render_template("edit.html", job=job)


# --- JOB-VERWALTUNG: NOTIZEN BEARBEITEN ---
@app.route("/notes/<int:id>", methods=["GET", "POST"])
@login_required
def notes(id):
    # Sucht die Bewerbung anhand der ID und stellt sicher, dass sie dem aktuellen Benutzer gehört (404 falls nicht)
    job = Job.query.filter_by(id=id, user_id=current_user.id).first_or_404()

    # Speichert die eingegebenen Notizen beim Absenden des Formulars (POST-Anfrage)
    if request.method == "POST":
        try:
            job.notes = request.form.get("notes", "").strip()
            db.session.commit()
            return redirect(url_for("index"))
        except Exception:
            # Rollback bei Datenbankfehlern
            db.session.rollback()
            flash(_("❌ Fehler beim Speichern!"))

    # Zeigt das Notizen-Formular bei einer GET-Anfrage an
    return render_template("notes.html", job=job)


# --- RECHTLICHE HINWEISE: IMPRESSUM ---
@app.route("/impressum")
def impressum():
    # Zeigt die Impressums-Seite (rechtliche Informationen) an
    return render_template("impressum.html")


# --- RECHTLICHE HINWEISE: DATENSCHUTZERKLÄRUNG ---
@app.route("/datenschutz")
def datenschutz():
    # Zeigt die Datenschutzerklärung (DSGVO-Hinweise) an
    return render_template("datenschutzerklaerung.html")


# --- ANWENDUNGSSTART (ENTRY POINT) ---
if __name__ == "__main__":
    # Startet den Flask-Entwicklungsserver im Debug-Modus
    # Der Debug-Modus ermöglicht automatisches Neuladen bei Codeänderungen und detaillierte Fehlermeldungen
    app.run(debug=True)  # pragma: no cover
