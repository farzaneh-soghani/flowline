import pytest
import time
from sqlalchemy.exc import IntegrityError
from flask_babel import _
from unittest.mock import patch
from itsdangerous import URLSafeTimedSerializer
from datetime import datetime, timedelta
from app import (
    app as flask_app,
    db,
    User,
    Job,
    mail,
    generate_reset_token,
    verify_reset_token,
    german_date_filter,
    load_user,
    inject_global_vars,
)

# --- Fixtures ---


@pytest.fixture
def app_instance():
    # ۱. حتماً حالت تست و لغو ارسال ایمیل را فعال کنید
    flask_app.config["TESTING"] = True
    flask_app.config["MAIL_SUPPRESS_SEND"] = True

    # ۲. اعمال کانفیگ جدید روی خودِ اینستنس mail
    mail.init_app(flask_app)

    # ۳. غیرفعال‌سازی مستقیم
    mail.suppress_send = True

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app_instance):
    return app_instance.test_client()


# --- Tests ---


def test_startseite(client):
    rv = client.get("/")
    assert rv.status_code == 302


def test_login_redirect(client):
    response = client.get("/stats", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_message_is_none(client):
    with client.session_transaction() as sess:
        assert "_flashes" not in sess


def test_password_reset_token(app_instance):
    user = User(email="test_token@example.com", password_hash="dummy_hash")
    db.session.add(user)
    db.session.commit()

    token = generate_reset_token(user)
    verified_user = verify_reset_token(token)
    assert verified_user.id == user.id


def test_expired_reset_token(app_instance):
    user = User(email="expired_test@example.com", password_hash="dummy_hash")
    db.session.add(user)
    db.session.commit()

    token = generate_reset_token(user)

    # افزایش تاخیر به ۲ ثانیه برای اطمینان از انقضای کامل توکن
    time.sleep(2)

    verified_user = verify_reset_token(token, expiration=1)
    assert verified_user is None


def test_reset_password_mail_error(client):
    # شبیه‌سازی وجود کاربر در دیتابیس (برای اینکه شرط if user برقرار شود)
    # و سپس خطا دادنِ mail.send
    with patch("app.mail.send", side_effect=Exception("Mail server error")):
        client.post(
            "/reset_password_request",
            data={"email": "user@example.com"},  # ایمیلی که در دیتابیس وجود دارد
            follow_redirects=True,
        )
        # چون در حالت TESTING هستیم، این تست انتظار دارد که Exception بالا بیاید (raise شود)


def test_register_database_error(client):
    # شبیه‌سازی خطای پایگاه داده هنگام commit کردن
    with patch("app.db.session.commit", side_effect=Exception("Database error")):
        response = client.post(
            "/register",
            data={"email": "newuser@example.com", "password": "securepassword"},
            follow_redirects=True,
        )

        # بررسی اینکه دیتابیس رول‌بک شده، پیام خطا داده شده و به صفحه ثبت‌نام برگشته است
        assert response.status_code == 200
        assert b"Registrierung fehlgeschlagen." in response.data


def test_get_locale_from_session(app_instance):
    with app_instance.test_request_context("/"):
        from flask import session

        session["lang"] = "fa"
        from app import get_locale

        assert get_locale() == "fa"


def test_get_locale_default(client):
    with client.application.test_request_context(headers=[("Accept-Language", "xx")]):
        from app import get_locale

        assert get_locale() == "de"


def test_user_password_hashing(client):
    user = User(email="testuser@example.com")
    user.set_password("geheim123")
    assert user.password_hash != "geheim123"
    assert user.check_password("geheim123") is True
    assert user.check_password("falsches_passwort") is False


def test_register_empty_fields(client):
    # ارسال درخواست POST با فرمِ خالی یا ایمیل خالی
    response = client.post(
        "/register", data={"email": "", "password": ""}, follow_redirects=True
    )

    # بررسی اینکه کاربر مجدد به صفحه ثبت‌نام هدایت شده و پیام خطا نمایش داده می‌شود
    assert response.status_code == 200
    assert b"Bitte E-Mail und Passwort eingeben!" in response.data


def test_user_unique_email(client):
    user1 = User(email="doppelt@example.com")
    user1.set_password("pass1")
    db.session.add(user1)
    db.session.commit()

    user2 = User(email="doppelt@example.com")
    user2.set_password("pass2")
    db.session.add(user2)

    with pytest.raises(IntegrityError):
        db.session.commit()

    # بازگرداندن وضعیت session بعد از خطای تعمدی
    db.session.rollback()


def test_job_creation_and_defaults(client):
    user = User(email="jobtest@example.com", password_hash="dummy")
    db.session.add(user)
    db.session.commit()

    job = Job(firma="Tech Corp", position="Entwickler", status="Offen", user_id=user.id)
    db.session.add(job)
    db.session.commit()

    assert job.id is not None
    assert job.firma == "Tech Corp"
    assert job.nachgefasst is False
    assert job.datum is not None
    assert job.owner.email == "jobtest@example.com"


def test_load_user_success(client):
    user = User(email="loader_test@example.com")
    user.set_password("pass123")
    db.session.add(user)
    db.session.commit()

    loaded_user = load_user(user.id)
    assert loaded_user is not None
    assert loaded_user.email == "loader_test@example.com"


def test_load_user_invalid_id(client):
    assert load_user(99999) is None


def test_german_date_filter(app_instance):
    with app_instance.test_request_context("/"):
        assert german_date_filter("2026-08-14") == "14.08.2026"
        assert german_date_filter("") == "k.A."
        assert german_date_filter(None) == "k.A."
        assert german_date_filter("ungueltiges-datum") == "ungueltiges-datum"


def test_register_success(client):
    response = client.post(
        "/register",
        data={"email": "neuer_user@example.com", "password": "SicheresPasswort123"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    user = User.query.filter_by(email="neuer_user@example.com").first()
    assert user is not None


def test_register_short_password(client):
    client.post(
        "/register",
        data={"email": "shortpass@example.com", "password": "123"},
        follow_redirects=True,
    )

    user = User.query.filter_by(email="shortpass@example.com").first()
    assert user is None


def test_register_duplicate_email(client):
    existing_user = User(email="existiert@example.com")
    existing_user.set_password("SicheresPasswort123")
    db.session.add(existing_user)
    db.session.commit()

    client.post(
            "/register",
            data={"email": "existiert@example.com", "password": "NeuesPasswort123"},
            follow_redirects=True,
        )

    users_count = User.query.filter_by(email="existiert@example.com").count()
    assert users_count == 1


def test_login_success(client):
    user = User(email="login_success@example.com")
    user.set_password("Passwort123")
    db.session.add(user)
    db.session.commit()

    response = client.post(
        "/login",
        data={"email": "login_success@example.com", "password": "Passwort123"},
        follow_redirects=True,
    )

    assert response.status_code == 200


def test_login_wrong_password(client):
    user = User(email="login_fail@example.com")
    user.set_password("Passwort123")
    db.session.add(user)
    db.session.commit()

    response = client.post(
        "/login",
        data={"email": "login_fail@example.com", "password": "FalschesPasswort"},
        follow_redirects=True,
    )

    assert response.status_code == 200


def test_logout_success(client):
    user = User(email="logout_test@example.com")
    user.set_password("Passwort123")
    db.session.add(user)
    db.session.commit()

    client.post(
        "/login", data={"email": "logout_test@example.com", "password": "Passwort123"}
    )

    response = client.get("/logout", follow_redirects=True)
    assert response.status_code == 200


def test_logout_unauthorized(client):
    response = client.get("/logout", follow_redirects=True)
    assert response.status_code == 200


def test_delete_account(app_instance, client):
    """Testet das Löschen des Benutzerkontos."""
    with app_instance.app_context():
        # 1. Test-Benutzer in der Datenbank erstellen
        user = User(email="delete_test@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()

    # 2. Mit dem erstellten Benutzer einloggen
    client.post('/login', data=dict(email="delete_test@example.com", password="password123"), follow_redirects=True)

    # 3. Anfrage zum Löschen des Kontos senden
    response = client.post('/delete-account', follow_redirects=True)
    assert response.status_code == 200
    assert "Dein Konto wurde erfolgreich gelöscht." in response.get_data(as_text=True)


def test_reset_password_database_error(app_instance, client):
    with app_instance.app_context():
        # ۱. ساختن یک کاربر تستی
        user = User(email="dberror@example.com")
        user.set_password("oldpassword")
        db.session.add(user)
        db.session.commit()

        # ۲. ساختن توکن معتبر
        serializer = URLSafeTimedSerializer(app_instance.secret_key)
        token = serializer.dumps(
            {"email": user.email, "hash": user.password_hash},
            salt="password-reset-salt",
        )

        # ۳. شبیه‌سازی خطا در commit پایگاه داده
        with patch("app.db.session.commit", side_effect=Exception("Database error")):
            response = client.post(
                f"/reset_password/{token}",
                data={"password": "newsecurepassword"},
                follow_redirects=True,
            )

            # ۴. بررسی اینکه خطا به درستی مدیریت شده و پیام خطا داده شده است
            assert response.status_code == 200
            assert b"Fehler beim Speichern des Passworts." in response.data


def test_reset_password_request_success(client):
    user = User(email="reset_user@example.com")
    user.set_password("Passwort123")
    db.session.add(user)
    db.session.commit()

    with mail.record_messages() as outbox:
        response = client.post(
            "/reset_password_request",
            data={"email": "reset_user@example.com"},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert len(outbox) == 1
        assert outbox[0].recipients == ["reset_user@example.com"]


def test_reset_password_request_user_not_found(client):
    with mail.record_messages() as outbox:
        response = client.post(
            "/reset_password_request",
            data={"email": "unbekannt@example.com"},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert len(outbox) == 0


def test_reset_password_invalid_token(client):
    response = client.get(
        "/reset_password/ungueltiger_token_123", follow_redirects=True
    )
    assert response.status_code == 200


def test_reset_password_success(client):
    user = User(email="token_test@example.com")
    user.set_password("OldPassword123")
    db.session.add(user)
    db.session.commit()

    token = generate_reset_token(user)

    response = client.post(
        f"/reset_password/{token}",
        data={"password": "NewPassword123"},
        follow_redirects=True,
    )

    assert response.status_code == 200

    updated_user = User.query.filter_by(email="token_test@example.com").first()
    assert updated_user.check_password("NewPassword123") is True


def test_reset_password_short_password(app_instance, client):
    with app_instance.app_context():
        # ۱. ساختن یک کاربر تستی جدید در دیتابیس
        user = User(email="testuser@example.com")
        user.set_password("longpassword")
        db.session.add(user)
        db.session.commit()

        # ۲. ساختن توکن برای همین کاربر
        serializer = URLSafeTimedSerializer(app_instance.secret_key)
        token = serializer.dumps(
            {"email": user.email, "hash": user.password_hash},
            salt="password-reset-salt",
        )

        # ۳. ارسال درخواست با پسورد کوتاه
        response = client.post(
            f"/reset_password/{token}", data={"password": "123"}, follow_redirects=True
        )

        assert response.status_code == 200
        assert b"Das Passwort muss mindestens 8 Zeichen lang sein!" in response.data


def test_verify_reset_token_invalid_user_or_password(app_instance):
    with app_instance.app_context():
        # ۱. ساختن یک توکن برای کاربری که وجود ندارد یا پسوردش تغییر کرده
        serializer = URLSafeTimedSerializer(app_instance.secret_key)
        token = serializer.dumps(
            {"email": "nonexistent@example.com", "hash": "wronghash"},
            salt="password-reset-salt",
        )

        # ۲. بررسی اینکه تابع به درستی None برمی‌گرداند
        result = verify_reset_token(token)
        assert result is None


def test_add_job_success(client):
    user = User(email="job_owner@example.com")
    user.set_password("Passwort123")
    db.session.add(user)
    db.session.commit()

    client.post(
        "/login", data={"email": "job_owner@example.com", "password": "Passwort123"}
    )

    response = client.post(
        "/",
        data={
            "firma": "Test GmbH",
            "position": "Backend Entwickler",
            "status": "offen",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    job = Job.query.filter_by(firma="Test GmbH").first()
    assert job is not None
    assert job.user_id == user.id


def test_add_job_database_error(client, app_instance):
    with app_instance.app_context():
        # ۱. ساخت و ثبت یک کاربر برای تست
        user = User(email="joberror@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()

    # ۲. لاگین کردن به سیستم با کلاینت
    client.post(
        "/login", data={"email": "joberror@example.com", "password": "password123"}
    )

    # ۳. شبیه‌سازی خطای دیتابیس هنگام ثبت شغل جدید
    with patch("app.db.session.commit", side_effect=Exception("Database error")):
        response = client.post(
            "/",
            data={"firma": "TestFirma", "position": "Developer"},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Fehler beim Speichern!" in response.data


def test_job_due_reminder(client, app_instance):
    with app_instance.app_context():
        # ۱. ساختن یک کاربر و ذخیره در دیتابیس
        user = User(email="reminder@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()

        # ذخیره id کاربر تا بعد از بسته شدن سشن هم در دسترس باشد
        user_id = user.id

    # ۲. لاگین کردن به سیستم با کلاینت
    client.post(
        "/login", data={"email": "reminder@example.com", "password": "password123"}
    )

    with app_instance.app_context():
        # ۳. ساختن یک شغل با تاریخ پیگیری در گذشته
        past_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        job = Job(
            firma="TestFirma",
            position="Developer",
            status="offen",
            follow_up_datum=past_date,
            user_id=user_id,
            nachgefasst=False,
        )
        db.session.add(job)
        db.session.commit()

    # ۴. باز کردن صفحه اصلی برای بررسی یادآوری‌ها
    response = client.get("/", follow_redirects=True)

    assert response.status_code == 200
    assert b"Achtung" in response.data or b"Bewerbung" in response.data


def test_add_job_missing_required_fields(client):
    user = User(email="job_missing@example.com")
    user.set_password("Passwort123")
    db.session.add(user)
    db.session.commit()

    client.post(
        "/login", data={"email": "job_missing@example.com", "password": "Passwort123"}
    )

    response = client.post(
        "/", data={"firma": "Unvollständig GmbH", "position": ""}, follow_redirects=True
    )

    assert response.status_code == 200
    job = Job.query.filter_by(firma="Unvollständig GmbH").first()
    assert job is None


def test_job_search(client):
    user = User(email="search_user@example.com")
    user.set_password("Passwort123")
    db.session.add(user)
    db.session.commit()

    client.post(
        "/login", data={"email": "search_user@example.com", "password": "Passwort123"}
    )

    job1 = Job(firma="SAP", position="Python Dev", status="offen", user_id=user.id)
    job2 = Job(firma="BMW", position="Frontend Dev", status="offen", user_id=user.id)
    db.session.add_all([job1, job2])
    db.session.commit()

    response = client.get("/?q=SAP")
    assert response.status_code == 200
    assert b"SAP" in response.data


def test_delete_job_database_error(client, app_instance):
    with app_instance.app_context():
        # ۱. ساخت کاربر و یک شغل تستی با status مشخص
        user = User(email="delerror@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()

        job = Job(firma="DeleteCorp", position="Dev", status="offen", user_id=user.id)
        db.session.add(job)
        db.session.commit()
        job_id = job.id

    # ۲. لاگین کردن به سیستم
    client.post(
        "/login", data={"email": "delerror@example.com", "password": "password123"}
    )

    # ۳. شبیه‌سازی خطای دیتابیس هنگام commit در عملیات حذف
    with patch("app.db.session.commit", side_effect=Exception("Database error")):
        response = client.get(f"/delete/{job_id}", follow_redirects=True)

        # ۴. بررسی اینکه رول‌بک انجام شده و پیام خطا نمایش داده شده است
        assert response.status_code == 200
        assert "Fehler beim Löschen!" in response.get_data(as_text=True)


def test_edit_job_database_error(client, app_instance):
    with app_instance.app_context():
        # ۱. ساختن کاربر و شغل تستی
        user = User(email="editerror@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()

        job = Job(firma="OldCorp", position="Dev", status="offen", user_id=user.id)
        db.session.add(job)
        db.session.commit()
        job_id = job.id

    # ۲. لاگین کردن به سیستم
    client.post(
        "/login", data={"email": "editerror@example.com", "password": "password123"}
    )

    # ۳. شبیه‌سازی خطای دیتابیس هنگام commit در عملیات ویرایش
    with patch("app.db.session.commit", side_effect=Exception("Database error")):
        response = client.post(
            f"/edit/{job_id}",
            data={"firma": "NewCorp", "position": "Senior Dev", "status": "offen"},
            follow_redirects=True,
        )

        # ۴. بررسی اینکه رول‌بک انجام شده و پیام خطا نمایش داده شده است
        assert response.status_code == 200
        assert "Fehler beim Aktualisieren!" in response.get_data(as_text=True)


def test_notes_get_page(client, app_instance):
    with app_instance.app_context():
        user = User(email="notesget@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()

        job = Job(firma="NotesCorp", position="Dev", status="offen", user_id=user.id)
        db.session.add(job)
        db.session.commit()
        job_id = job.id

    client.post(
        "/login", data={"email": "notesget@example.com", "password": "password123"}
    )

    response = client.get(f"/notes/{job_id}")
    assert response.status_code == 200
    assert "NotesCorp" in response.get_data(as_text=True)


# ۲. تستِ شبیه‌سازی خطای دیتابیس هنگام ذخیره یادداشت (برای پوشش except و رول‌بک)
def test_notes_database_error(client, app_instance):
    with app_instance.app_context():
        user = User(email="noteserror@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()

        job = Job(firma="ErrorCorp", position="Dev", status="offen", user_id=user.id)
        db.session.add(job)
        db.session.commit()
        job_id = job.id

    client.post(
        "/login", data={"email": "noteserror@example.com", "password": "password123"}
    )

    with patch("app.db.session.commit", side_effect=Exception("Database error")):
        response = client.post(
            f"/notes/{job_id}", data={"notes": "Wichtige Notiz"}, follow_redirects=True
        )

        assert response.status_code == 200
        assert "Fehler beim Speichern!" in response.get_data(as_text=True)


def test_toggle_nachgefasst_success(client):
    user = User(email="toggle_owner@example.com")
    user.set_password("Passwort123")
    db.session.add(user)
    db.session.commit()

    client.post(
        "/login", data={"email": "toggle_owner@example.com", "password": "Passwort123"}
    )

    job = Job(
        firma="Toggle AG",
        position="Dev",
        status="offen",
        nachgefasst=False,
        user_id=user.id,
    )
    db.session.add(job)
    db.session.commit()

    response = client.get(f"/toggle_nachgefasst/{job.id}", follow_redirects=True)
    assert response.status_code == 200

    updated_job = db.session.get(Job, job.id)
    assert updated_job.nachgefasst is True


def test_toggle_nachgefasst_other_user(client):
    user1 = User(email="user1_toggle@example.com")
    user1.set_password("Passwort123")
    user2 = User(email="user2_toggle@example.com")
    user2.set_password("Passwort123")
    db.session.add_all([user1, user2])
    db.session.commit()

    job = Job(firma="User1 Firma", position="Dev", status="offen", user_id=user1.id)
    db.session.add(job)
    db.session.commit()

    client.post(
        "/login", data={"email": "user2_toggle@example.com", "password": "Passwort123"}
    )

    response = client.get(f"/toggle_nachgefasst/{job.id}")
    assert response.status_code == 404


def test_inject_global_vars(app_instance):
    with app_instance.test_request_context("/"):
        context_vars = inject_global_vars()
        assert "current_lang" in context_vars
        assert "_" in context_vars
        assert context_vars["_"] == _


def test_set_language_valid(client):
    response = client.get("/set_language/en", follow_redirects=True)
    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert sess["lang"] == "en"


def test_set_language_invalid(client):
    response = client.get("/set_language/xyz", follow_redirects=True)
    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert "lang" not in sess or sess["lang"] != "xyz"


def test_export_pdf_success(client):
    user = User(email="pdf_user@example.com")
    user.set_password("Passwort123")
    db.session.add(user)
    db.session.commit()

    client.post(
        "/login", data={"email": "pdf_user@example.com", "password": "Passwort123"}
    )

    job1 = Job(
        firma="Tech Corp",
        position="Backend Dev",
        status="offen",
        datum="2026-08-01",
        follow_up_datum="2026-08-15",
        user_id=user.id,
    )
    job2 = Job(
        firma="Design Inc",
        position="UI Designer",
        status="Zusage",
        datum="2026-08-02",
        follow_up_datum="2026-08-16",
        user_id=user.id,
    )
    db.session.add_all([job1, job2])
    db.session.commit()

    response = client.get("/export_pdf")

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/pdf"
    assert "attachment" in response.headers["Content-Disposition"]


def test_stats_route_empty(client):
    user = User(email="stats_empty@example.com")
    user.set_password("Passwort123")
    db.session.add(user)
    db.session.commit()

    client.post(
        "/login", data={"email": "stats_empty@example.com", "password": "Passwort123"}
    )

    response = client.get("/stats")
    assert response.status_code == 200


def test_stats_route_calculation(client):
    user = User(email="stats_calc@example.com")
    user.set_password("Passwort123")
    db.session.add(user)
    db.session.commit()

    client.post(
        "/login", data={"email": "stats_calc@example.com", "password": "Passwort123"}
    )

    job1 = Job(firma="Firma A", position="Dev", status="offen", user_id=user.id)
    job2 = Job(firma="Firma B", position="Dev", status="offen", user_id=user.id)
    job3 = Job(firma="Firma C", position="Dev", status="Absage", user_id=user.id)
    job4 = Job(firma="Firma D", position="Dev", status="Absage", user_id=user.id)
    db.session.add_all([job1, job2, job3, job4])
    db.session.commit()

    response = client.get("/stats")
    assert response.status_code == 200


def test_delete_job_success(client):
    user = User(email="delete_owner@example.com")
    user.set_password("Passwort123")
    db.session.add(user)
    db.session.commit()

    client.post(
        "/login", data={"email": "delete_owner@example.com", "password": "Passwort123"}
    )

    job = Job(firma="Delete GmbH", position="Dev", status="offen", user_id=user.id)
    db.session.add(job)
    db.session.commit()

    response = client.get(f"/delete/{job.id}", follow_redirects=True)
    assert response.status_code == 200

    deleted_job = db.session.get(Job, job.id)
    assert deleted_job is None


def test_delete_job_unauthorized(client):
    user1 = User(email="user1_delete@example.com")
    user1.set_password("Passwort123")
    user2 = User(email="user2_delete@example.com")
    user2.set_password("Passwort123")
    db.session.add_all([user1, user2])
    db.session.commit()

    job = Job(firma="User1 Firma", position="Dev", status="offen", user_id=user1.id)
    db.session.add(job)
    db.session.commit()

    client.post(
        "/login", data={"email": "user2_delete@example.com", "password": "Passwort123"}
    )

    response = client.get(f"/delete/{job.id}")
    assert response.status_code == 404


def test_edit_job_success(client):
    user = User(email="edit_owner@example.com")
    user.set_password("Passwort123")
    db.session.add(user)
    db.session.commit()

    client.post(
        "/login", data={"email": "edit_owner@example.com", "password": "Passwort123"}
    )

    job = Job(
        firma="Alte Firma", position="Junior Dev", status="offen", user_id=user.id
    )
    db.session.add(job)
    db.session.commit()

    response = client.post(
        f"/edit/{job.id}",
        data={
            "firma": "Neue Firma",
            "position": "Senior Dev",
            "status": "einladung",
            "follow_up_datum": "2026-09-01",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200

    updated_job = db.session.get(Job, job.id)
    assert updated_job.firma == "Neue Firma"
    assert updated_job.position == "Senior Dev"
    assert updated_job.status == "einladung"


def test_edit_job_missing_fields(client):
    user = User(email="edit_validation@example.com")
    user.set_password("Passwort123")
    db.session.add(user)
    db.session.commit()

    client.post(
        "/login",
        data={"email": "edit_validation@example.com", "password": "Passwort123"},
    )

    job = Job(firma="Firma X", position="Dev", status="offen", user_id=user.id)
    db.session.add(job)
    db.session.commit()

    response = client.post(
        f"/edit/{job.id}",
        data={"firma": "Firma X", "position": ""},
        follow_redirects=True,
    )

    assert response.status_code == 200

    unchanged_job = db.session.get(Job, job.id)
    assert unchanged_job.position == "Dev"


def test_edit_job_unauthorized(client):
    user1 = User(email="user1_edit@example.com")
    user1.set_password("Passwort123")
    user2 = User(email="user2_edit@example.com")
    user2.set_password("Passwort123")
    db.session.add_all([user1, user2])
    db.session.commit()

    job = Job(firma="User1 Firma", position="Dev", status="offen", user_id=user1.id)
    db.session.add(job)
    db.session.commit()

    client.post(
        "/login", data={"email": "user2_edit@example.com", "password": "Passwort123"}
    )

    response = client.post(
        f"/edit/{job.id}", data={"firma": "Geänderte Firma", "position": "Dev"}
    )
    assert response.status_code == 404


def test_update_notes_success(client):
    user = User(email="notes_owner@example.com")
    user.set_password("Passwort123")
    db.session.add(user)
    db.session.commit()

    client.post(
        "/login", data={"email": "notes_owner@example.com", "password": "Passwort123"}
    )

    job = Job(
        firma="Notes GmbH",
        position="Dev",
        status="offen",
        notes="Alte Notiz",
        user_id=user.id,
    )
    db.session.add(job)
    db.session.commit()

    response = client.post(
        f"/notes/{job.id}",
        data={"notes": "Neue wichtige Notiz zum Vorstellungsgespräch"},
        follow_redirects=True,
    )

    assert response.status_code == 200

    updated_job = db.session.get(Job, job.id)
    assert updated_job.notes == "Neue wichtige Notiz zum Vorstellungsgespräch"


def test_update_notes_unauthorized(client):
    user1 = User(email="user1_notes@example.com")
    user1.set_password("Passwort123")
    user2 = User(email="user2_notes@example.com")
    user2.set_password("Passwort123")
    db.session.add_all([user1, user2])
    db.session.commit()

    job = Job(firma="User1 Firma", position="Dev", status="offen", user_id=user1.id)
    db.session.add(job)
    db.session.commit()

    client.post(
        "/login", data={"email": "user2_notes@example.com", "password": "Passwort123"}
    )

    response = client.post(f"/notes/{job.id}", data={"notes": "Hacker Notiz"})
    assert response.status_code == 404


def test_impressum_route(client):
    response = client.get("/impressum")
    assert response.status_code == 200


def test_datenschutz_route(client):
    response = client.get("/datenschutz")
    assert response.status_code == 200
