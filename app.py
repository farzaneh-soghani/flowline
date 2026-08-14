import os
from dotenv import load_dotenv

load_dotenv()

import io
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer
from flask_mail import Mail, Message
from flask_babel import Babel, gettext as _

# Imports für die PDF-Generierung
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

app = Flask(__name__)

# --- CONFIGURATION ---
app.secret_key = os.getenv('SECRET_KEY') or os.urandom(24)

db_url = os.getenv('DATABASE_URL', 'sqlite:///flowline.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- MAIL CONFIGURATION (SECURE) ---
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = ('FlowLine Support', os.getenv('MAIL_USERNAME'))

mail = Mail(app)
db = SQLAlchemy(app)

# --- LOGIN MANAGER ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = None


# --- HELPER FUNCTIONS FOR PASSWORD RESET ---
def generate_reset_token(user):
    serializer = URLSafeTimedSerializer(app.secret_key)
    return serializer.dumps({'email': user.email, 'hash': user.password_hash}, salt='password-reset-salt')


def verify_reset_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(app.secret_key)
    try:
        data = serializer.loads(token, salt='password-reset-salt', max_age=expiration)
        email = data.get('email')
        token_hash = data.get('hash')
        
        user = User.query.filter_by(email=email).first()
        if not user or user.password_hash != token_hash:
            return None
            
        return user
    except Exception:
        return None


# --- BABEL LOCALE SELECTOR ---
def get_locale():
    if 'lang' in session:
        return session['lang']
    return request.accept_languages.best_match(['de', 'en', 'fa', 'ar', 'tr']) or 'de'

babel = Babel(app, locale_selector=get_locale)


# --- DATENBANK-MODELLE ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    jobs = db.relationship('Job', backref='owner', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='scrypt')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    firma = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    datum = db.Column(db.String(20), default=lambda: datetime.now().strftime('%Y-%m-%d'))
    follow_up_datum = db.Column(db.String(20), nullable=True)
    nachgefasst = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text, default='')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        print(f"Fehler beim Erstellen der Tabellen: {e}")


# --- JINJA FILTER FOR GERMAN DATE FORMAT ---
@app.template_filter('german_date')
def german_date_filter(date_str):
    if not date_str:
        return _('k.A.')  # 👈 علامت‌گذاری شد
    try:
        dt = datetime.strptime(str(date_str), '%Y-%m-%d')
        return dt.strftime('%d.%m.%Y')
    except ValueError:
        return str(date_str)


# --- AUTHENTIFIZIERUNG ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash(_('❌ Bitte E-Mail und Passwort eingeben!'))  # 👈 علامت‌گذاری شد
            return redirect(url_for('register'))

        if len(password) < 8:
            flash(_('❌ Das Passwort muss mindestens 8 Zeichen lang sein!'))  # 👈 علامت‌گذاری شد
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash(_('❌ Diese E-Mail-Adresse ist bereits registriert!'))  # 👈 علامت‌گذاری شد
            return redirect(url_for('register'))

        try:
            new_user = User(email=email)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('login'))
        except Exception:
            db.session.rollback()
            flash(_('❌ Registrierung fehlgeschlagen.'))  # 👈 علامت‌گذاری شد
            return redirect(url_for('register'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash(_('❌ Ungültige E-Mail-Adresse oder Passwort!'))  # 👈 علامت‌گذاری شد

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            token = generate_reset_token(user)
            reset_url = url_for('reset_password', token=token, _external=True)
            
            # 👈 موضوع و بدنه ایمیل قابل ترجمه شدند
            subject_text = _("Passwort zurücksetzen - FlowLine")
            body_text = _("Hallo,\n\nSie haben eine Anfrage zum Zurücksetzen Ihres Passworts für FlowLine gestellt.\nKlicken Sie auf den folgenden Link, um ein neues Passwort zu vergeben:\n\n%(url)s\n\nDieser Link ist 1 Stunde lang gültig.\nWenn Sie diese Anfrage nicht gestellt haben, können Sie diese E-Mail einfach ignorieren.\n\nViele Grüße\nIhr FlowLine Team") % {'url': reset_url}

            msg = Message(subject_text, recipients=[user.email])
            msg.body = body_text
            
            try:
                mail.send(msg)
                flash(_('Ein Link zum Zurücksetzen des Passworts wurde an Ihre E-Mail gesendet.'))  # 👈 علامت‌گذاری شد
            except Exception as e:
                print(f"Fehler beim E-Mail-Versand: {e}")
                flash(_('❌ Fehler beim Senden der E-Mail. Bitte versuchen Sie es später erneut.'))  # 👈 علامت‌گذاری شد
                
            return redirect(url_for('login'))
        else:
            flash(_('❌ Diese E-Mail-Adresse wurde nicht gefunden.'))  # 👈 علامت‌گذاری شد

    return render_template('reset_request.html')


@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = verify_reset_token(token)
    if not user:
        flash(_('❌ Der Link ist ungültig, abgelaufen oder wurde bereits verwendet.'))  # 👈 علامت‌گذاری شد
        return redirect(url_for('reset_password_request'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        if len(password) < 8:
            flash(_('❌ Das Passwort muss mindestens 8 Zeichen lang sein!'))  # 👈 علامت‌گذاری شد
            return redirect(url_for('reset_password', token=token))

        try:
            user.set_password(password)
            db.session.commit()
            flash(_('✅ Passwort erfolgreich geändert! Sie können sich jetzt einloggen.'))  # 👈 علامت‌گذاری شد
            return redirect(url_for('login'))
        except Exception:
            db.session.rollback()
            flash(_('❌ Fehler beim Speichern des Passworts.'))  # 👈 علامت‌گذاری شد

    return render_template('reset_password.html', token=token)


# --- HAUPTSEITE ---

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    default_follow_up = (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')

    if request.method == 'POST':
        firma = request.form.get('firma', '').strip()
        position = request.form.get('position', '').strip()
        status = request.form.get('status', 'offen').strip()
        custom_follow_up = request.form.get('follow_up_datum', '').strip()

        if not custom_follow_up:
            custom_follow_up = default_follow_up

        if not firma or not position:
            flash(_('❌ Firma und Position sind Pflichtfelder!'))  # 👈 علامت‌گذاری شد
            return redirect(url_for('index'))

        try:
            new_job = Job(
                firma=firma,
                position=position,
                status=status,
                follow_up_datum=custom_follow_up,
                user_id=current_user.id,
                nachgefasst=False
            )
            db.session.add(new_job)
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash(_('❌ Fehler beim Speichern!'))  # 👈 علامت‌گذاری شد

        return redirect(url_for('index'))

    search_query = request.args.get('q', '').strip()

    query = Job.query.filter_by(user_id=current_user.id)
    if search_query:
        query = query.filter(
            (Job.firma.ilike(f'%{search_query}%')) |
            (Job.position.ilike(f'%{search_query}%')) |
            (Job.status.ilike(f'%{search_query}%'))
        )
    jobs = query.all()

    heute = datetime.now().strftime('%Y-%m-%d')
    erinnerungen_anzahl = 0
    active_statuses = ['offen', 'einladung']

    for job in jobs:
        if (job.follow_up_datum and 
            job.follow_up_datum <= heute and 
            job.status.lower() in active_statuses and 
            not job.nachgefasst):
            
            job.is_due = True
            erinnerungen_anzahl += 1
        else:
            job.is_due = False

    if erinnerungen_anzahl > 0 and not search_query:
        # 👈 استفاده از متغیر دینامیک در پیام صریح ترجمه
        flash(_('Achtung: Bei %(num)d Bewerbung(en) ist ein Nachfassen oder Termin fällig!') % {'num': erinnerungen_anzahl})

    return render_template('index.html', jobs=jobs, user=current_user, search_query=search_query, default_follow_up=default_follow_up)


@app.route('/toggle_nachgefasst/<int:job_id>')
@login_required
def toggle_nachgefasst(job_id):
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    job.nachgefasst = not job.nachgefasst
    db.session.commit()
    return redirect(request.referrer or url_for('index'))


@app.context_processor
def inject_global_vars():
    lang = get_locale()
    return dict(current_lang=lang, _=_)


@app.route('/set_language/<lang>')
def set_language(lang):
    if lang in ['de', 'en', 'fa', 'ar', 'tr']:
        session['lang'] = lang
    return redirect(request.referrer or url_for('index'))


# --- PDF EXPORT ROUTE ---

@app.route('/export_pdf')
@login_required
def export_pdf():
    jobs = Job.query.filter_by(user_id=current_user.id).all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=20
    )

    elements.append(Paragraph(f"{_('Bewerbungsübersicht')} - {current_user.email}", title_style))
    elements.append(Spacer(1, 10))

    data = [[_("Firma"), _("Position"), _("Datum"), _("Erinnerung"), _("Status")]]
    for j in jobs:
        datum_formatted = datetime.strptime(j.datum, '%Y-%m-%d').strftime('%d.%m.%Y') if j.datum else "-"
        
        # 👈 شرط جدید: اگر استتوس Zusage یا Absage بود، یادآوری خالی (-) شود
        status_lower = j.status.lower() if j.status else ""
        if status_lower in ["zusage", "absage"]:
            follow_up_formatted = "-"
        else:
            follow_up_formatted = datetime.strptime(j.follow_up_datum, '%Y-%m-%d').strftime('%d.%m.%Y') if j.follow_up_datum else "-"

        data.append([
            j.firma,
            j.position,
            datum_formatted,
            follow_up_formatted,
            j.status.capitalize()
        ])

    pdf_table = Table(data, colWidths=[110, 130, 80, 90, 80])
    pdf_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")])
    ]))

    elements.append(pdf_table)
    doc.build(elements)

    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Bewerbungen_{datetime.now().strftime('%Y%m%d')}.pdf",
        mimetype='application/pdf'
    )


# --- STATISTIK, BEARBEITEN, DELETE & NOTIZEN ---

@app.route('/stats')
@login_required
def stats():
    jobs = Job.query.filter_by(user_id=current_user.id).all()
    total = len(jobs)
    offen = len([j for j in jobs if j.status.lower() == 'offen'])
    offen_prozent = round((offen / total * 100), 1) if total > 0 else 0
    return render_template('stats.html', total=total, offen=offen, offen_prozent=offen_prozent)


@app.route('/delete/<int:id>')
@login_required
def delete_job(id):
    job = Job.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    try:
        db.session.delete(job)
        db.session.commit()
        flash(_('🗑️ Bewerbung gelöscht!'))  # 👈 علامت‌گذاری شد
    except Exception:
        db.session.rollback()
        flash(_('❌ Fehler beim Löschen!'))  # 👈 علامت‌گذاری شد
    return redirect(url_for('index'))


@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_job(id):
    job = Job.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        firma = request.form.get('firma', '').strip()
        position = request.form.get('position', '').strip()
        status = request.form.get('status', '').strip()
        follow_up = request.form.get('follow_up_datum', '').strip()

        if not firma or not position:
            flash(_('❌ Pflichtfelder ausfüllen!'))  # 👈 علامت‌گذاری شد
            return redirect(url_for('edit_job', id=id))

        try:
            job.firma = firma
            job.position = position
            job.status = status
            job.follow_up_datum = follow_up
            db.session.commit()
            return redirect(url_for('index'))
        except Exception:
            db.session.rollback()
            flash(_('❌ Fehler beim Aktualisieren!'))  # 👈 علامت‌گذاری شد

    return render_template('edit.html', job=job)


@app.route('/notes/<int:id>', methods=['GET', 'POST'])
@login_required
def notes(id):
    job = Job.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        try:
            job.notes = request.form.get('notes', '').strip()
            db.session.commit()
            return redirect(url_for('index'))
        except Exception:
            db.session.rollback()
            flash(_('❌ Fehler beim Speichern!'))  # 👈 علامت‌گذاری شد

    return render_template('notes.html', job=job)


@app.route('/impressum')
def impressum():
    return render_template('impressum.html')


@app.route('/datenschutz')
def datenschutz():
    return render_template('datenschutzerklaerung.html')


if __name__ == '__main__':
    app.run(debug=True)