-- Схема БД портала «Конференции.РФ» (SQLite)
-- users    - пользователи (обычные и администратор)
-- requests - заявки на бронирование помещения (связь: users 1 -> N requests)

CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    login      TEXT NOT NULL UNIQUE,
    password   TEXT NOT NULL,              -- хэш пароля
    full_name  TEXT NOT NULL,
    phone      TEXT NOT NULL,
    email      TEXT NOT NULL,
    role       TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user','admin')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS requests (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    room       TEXT NOT NULL,              -- название помещения (текстом)
    start_date TEXT NOT NULL,              -- дата начала, ISO ГГГГ-ММ-ДД
    payment    TEXT NOT NULL CHECK (payment IN ('При очном посещении','Перевод по СБП')),
    status     TEXT NOT NULL DEFAULT 'Новая'
               CHECK (status IN ('Новая','Мероприятие назначено','Завершено')),
    review     TEXT,                       -- отзыв (только после «Завершено»)
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
