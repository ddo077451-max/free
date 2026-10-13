"""
Модуль 4: API магазина (Flask + SQLite), порт 8080.
Запуск:  DB_PATH=/полный/путь/shop.db python app.py

!!! ВАЖНО: точные названия таблиц/полей и правила обработки лежат в
!!! Прил_4_ОЗ_КИМ_09.02.07-3-2027.pdf. Ниже - типовая схема магазина.
!!! На экзамене сверьте имена из блока SCHEMA и словарь STATUS_RU с приложением.
"""
import os
import sqlite3
from flask import Flask, jsonify, request

DB_PATH = os.environ.get("DB_PATH", "shop.db")

# ---- SCHEMA: поправьте под реальный дамп shop_db.sql ----
ORDERS_TABLE = "orders"          # id, user_id, status, total, created_at, city, street, house, ...
ITEMS_TABLE = "order_items"      # id, order_id, product_name, quantity, price
USERS_TABLE = "users"            # id, first_name, last_name

# ---- Состояния заказа: код в БД -> текст по-русски ----
STATUS_RU = {
    "new": "Новый",
    "paid": "Оплачен",
    "shipped": "Отправлен",
    "delivered": "Доставлен",
    "cancelled": "Отменён",
}

app = Flask(__name__)
app.json.ensure_ascii = False        # русский текст не экранируется
app.json.sort_keys = False           # порядок полей как в коде


class BadRequest(Exception):
    pass


def money(v):
    """Сумма/цена с двумя знаками после запятой."""
    return f"{float(v):.2f}"


def fmt_date(s):
    """ГГГГ-ММ-ДД[ ...] -> ДД.ММ.ГГГГ."""
    y, m, d = str(s)[:10].split("-")
    return f"{d}.{m}.{y}"


def build_order(db, o):
    user = db.execute(f"SELECT * FROM {USERS_TABLE} WHERE id=?", (o["user_id"],)).fetchone()
    buyer = " ".join(x for x in (user["last_name"], user["first_name"]) if x) if user else ""
    items = db.execute(f"SELECT * FROM {ITEMS_TABLE} WHERE order_id=? ORDER BY id", (o["id"],)).fetchall()
    address = ", ".join(str(o[k]) for k in ("city", "street", "house") if k in o.keys() and o[k])
    return {
        "id": o["id"],
        "customer": buyer,                                   # покупатель одной строкой
        "status": STATUS_RU.get(o["status"], o["status"]),   # состояние по-русски
        "total": money(o["total"]),
        "date": fmt_date(o["created_at"]),
        "address": address,                                  # адрес одной строкой
        "items_count": len(items),
        "items": [{
            "name": i["product_name"],
            "quantity": i["quantity"],
            "price": money(i["price"]),
        } for i in items],
    }


@app.get("/orders")
def orders():
    status = request.args.get("status")
    user_id = request.args.get("user_id")
    where, params = [], []

    if status is not None:
        if status not in STATUS_RU and status not in STATUS_RU.values():
            raise BadRequest("Недопустимое значение параметра status")
        code = next((k for k, v in STATUS_RU.items() if v == status), status)
        where.append("status=?")
        params.append(code)
    if user_id is not None:
        if not user_id.isdigit():
            raise BadRequest("Недопустимое значение параметра user_id")
        where.append("user_id=?")
        params.append(int(user_id))

    sql = f"SELECT * FROM {ORDERS_TABLE}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id ASC"                                # по возрастанию номера

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    try:
        return jsonify([build_order(db, o) for o in db.execute(sql, params).fetchall()])
    finally:
        db.close()


@app.errorhandler(BadRequest)
def on_400(e):
    return jsonify({"error": str(e)}), 400


@app.errorhandler(Exception)
def on_500(e):
    return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
