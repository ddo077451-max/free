"""
Портал «Конференции.РФ» - бэкенд (Flask + SQLite).
Запуск:  pip install flask   ->   python app.py   ->   http://localhost:5000
CSRF-защиты нет (в Flask по умолчанию её нет) - автотест сможет отправлять формы.
"""
import os
import re
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (Flask, g, render_template, request, redirect,
                   url_for, session, flash, abort)
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "conf.db")

ADMIN_LOGIN = "Conf2027"
ADMIN_PASSWORD = "Demo77"

STATUSES = ["Новая", "Мероприятие назначено", "Завершено"]
PAYMENTS = ["При очном посещении", "Перевод по СБП"]

app = Flask(__name__)
app.secret_key = "conf-2027-demo-secret"


# ---------------------------------------------------------------- БД
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Создаёт таблицы и учётную запись администратора."""
    db = sqlite3.connect(DB_PATH)
    with open(os.path.join(BASE, "schema.sql"), encoding="utf-8") as f:
        db.executescript(f.read())
    exists = db.execute("SELECT 1 FROM users WHERE login=?", (ADMIN_LOGIN,)).fetchone()
    if not exists:
        db.execute(
            "INSERT INTO users(login,password,full_name,phone,email,role) VALUES(?,?,?,?,?,'admin')",
            (ADMIN_LOGIN, generate_password_hash(ADMIN_PASSWORD),
             "Администратор", "8(000)000-00-00", "admin@conf.ru"))
    db.commit()
    db.close()


# ---------------------------------------------------------------- вспомогательное
def parse_date(text):
    """Принимает ДД.ММ.ГГГГ или ГГГГ-ММ-ДД, возвращает ISO-строку или None."""
    text = (text or "").strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


@app.template_filter("ru_date")
def ru_date(iso):
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return iso


def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


@app.context_processor
def inject_user():
    return {"user": current_user(), "STATUSES": STATUSES, "PAYMENTS": PAYMENTS}


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user():
            return redirect(url_for("login"))
        return fn(*a, **kw)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        u = current_user()
        if not u:
            return redirect(url_for("login"))
        if u["role"] != "admin":
            abort(403)
        return fn(*a, **kw)
    return wrapper


def validate_registration(f):
    """Возвращает словарь ошибок {поле: текст}."""
    e = {}
    if not re.fullmatch(r"[A-Za-z0-9]{6,}", f["login"]):
        e["login"] = "Логин: только латиница и цифры, не менее 6 символов"
    if len(f["password"]) < 8:
        e["password"] = "Пароль: не менее 8 символов"
    if not re.fullmatch(r"[А-Яа-яЁё ]+", f["full_name"]) or not f["full_name"].strip():
        e["full_name"] = "ФИО: только кириллица и пробелы"
    if not re.fullmatch(r"8\(\d{3}\)\d{3}-\d{2}-\d{2}", f["phone"]):
        e["phone"] = "Телефон в формате 8(XXX)XXX-XX-XX"
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", f["email"]):
        e["email"] = "Введите корректный e-mail"
    return e


# ---------------------------------------------------------------- авторизация
@app.route("/")
def index():
    u = current_user()
    if not u:
        return redirect(url_for("login"))
    return redirect(url_for("admin" if u["role"] == "admin" else "requests_list"))


@app.route("/register", methods=["GET", "POST"])
def register():
    errors, form = {}, {}
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip()
                for k in ("login", "password", "full_name", "phone", "email")}
        errors = validate_registration(form)
        for k, v in form.items():
            if not v:
                errors[k] = "Поле обязательно для заполнения"
        if not errors:
            db = get_db()
            if db.execute("SELECT 1 FROM users WHERE login=?", (form["login"],)).fetchone():
                errors["login"] = "Такой логин уже занят"
            else:
                db.execute(
                    "INSERT INTO users(login,password,full_name,phone,email) VALUES(?,?,?,?,?)",
                    (form["login"], generate_password_hash(form["password"]),
                     form["full_name"], form["phone"], form["email"]))
                db.commit()
                flash("Регистрация прошла успешно. Войдите в систему.", "ok")
                return redirect(url_for("login"))
    return render_template("register.html", errors=errors, form=form)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        login_ = request.form.get("login", "").strip()
        password = request.form.get("password", "")
        row = get_db().execute("SELECT * FROM users WHERE login=?", (login_,)).fetchone()
        if row and check_password_hash(row["password"], password):
            session["uid"] = row["id"]
            return redirect(url_for("admin" if row["role"] == "admin" else "requests_list"))
        error = "Неверный логин или пароль"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------- заявки пользователя
@app.route("/requests")
@login_required
def requests_list():
    u = current_user()
    rows = get_db().execute(
        "SELECT * FROM requests WHERE user_id=? ORDER BY id DESC", (u["id"],)).fetchall()
    return render_template("requests.html", rows=rows)


def read_request_form():
    room = request.form.get("room", "").strip()
    date_iso = parse_date(request.form.get("start_date"))
    payment = request.form.get("payment", "")
    errors = {}
    if not room:
        errors["room"] = "Укажите помещение"
    if not date_iso:
        errors["start_date"] = "Дата в формате ДД.ММ.ГГГГ"
    if payment not in PAYMENTS:
        errors["payment"] = "Выберите способ оплаты"
    return room, date_iso, payment, errors


@app.route("/requests/new", methods=["GET", "POST"])
@login_required
def request_new():
    errors, form = {}, {}
    if request.method == "POST":
        room, date_iso, payment, errors = read_request_form()
        form = {"room": room, "start_date": request.form.get("start_date", ""), "payment": payment}
        if not errors:
            db = get_db()
            db.execute("INSERT INTO requests(user_id,room,start_date,payment) VALUES(?,?,?,?)",
                       (current_user()["id"], room, date_iso, payment))
            db.commit()
            return redirect(url_for("requests_list"))
    return render_template("request_form.html", errors=errors, form=form, edit=False)


@app.route("/requests/<int:rid>/edit", methods=["GET", "POST"])
@login_required
def request_edit(rid):
    db = get_db()
    row = db.execute("SELECT * FROM requests WHERE id=? AND user_id=?",
                     (rid, current_user()["id"])).fetchone()
    if not row:
        abort(404)
    errors = {}
    form = {"room": row["room"], "start_date": ru_date(row["start_date"]), "payment": row["payment"]}
    if request.method == "POST":
        room, date_iso, payment, errors = read_request_form()
        form = {"room": room, "start_date": request.form.get("start_date", ""), "payment": payment}
        if not errors:
            db.execute("UPDATE requests SET room=?, start_date=?, payment=? WHERE id=?",
                       (room, date_iso, payment, rid))
            db.commit()
            return redirect(url_for("requests_list"))
    return render_template("request_form.html", errors=errors, form=form, edit=True, rid=rid)


@app.route("/requests/<int:rid>/delete", methods=["POST"])
@login_required
def request_delete(rid):
    db = get_db()
    db.execute("DELETE FROM requests WHERE id=? AND user_id=?", (rid, current_user()["id"]))
    db.commit()
    return redirect(url_for("requests_list"))


@app.route("/requests/<int:rid>/review", methods=["POST"])
@login_required
def request_review(rid):
    db = get_db()
    row = db.execute("SELECT * FROM requests WHERE id=? AND user_id=?",
                     (rid, current_user()["id"])).fetchone()
    if not row:
        abort(404)
    if row["status"] != "Завершено":
        flash("Отзыв можно оставить только после завершения мероприятия.", "err")
    else:
        db.execute("UPDATE requests SET review=? WHERE id=?",
                   (request.form.get("review", "").strip(), rid))
        db.commit()
        flash("Спасибо за отзыв!", "ok")
    return redirect(url_for("requests_list"))


# ---------------------------------------------------------------- панель администратора
@app.route("/admin")
@admin_required
def admin():
    status = request.args.get("status", "")
    sql = ("SELECT r.*, u.login, u.full_name FROM requests r "
           "JOIN users u ON u.id=r.user_id")
    params = ()
    if status in STATUSES:
        sql += " WHERE r.status=?"
        params = (status,)
    rows = get_db().execute(sql + " ORDER BY r.id DESC", params).fetchall()
    return render_template("admin.html", rows=rows, current=status)


@app.route("/admin/<int:rid>/status", methods=["POST"])
@admin_required
def admin_status(rid):
    status = request.form.get("status", "")
    if status not in STATUSES:
        abort(400)
    db = get_db()
    db.execute("UPDATE requests SET status=? WHERE id=?", (status, rid))
    db.commit()
    return redirect(url_for("admin", status=request.args.get("status", "")))


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
