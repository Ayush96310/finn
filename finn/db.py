import json
import sqlite3
from contextlib import contextmanager

from .config import DB_PATH

SCHEMA = """
create table if not exists prices (
    symbol text, date text, open real, high real, low real, close real, volume integer,
    primary key (symbol, date)
);

create table if not exists filings (
    id text primary key,
    symbol text,
    filed_at text,
    nse_category text,
    subject text,
    attachment text,
    category text,
    subtype text,
    score integer,
    tier text,
    summary text,
    card text,
    enriched integer default 0
);
create index if not exists filings_time on filings (filed_at);

create table if not exists alerts (
    id text primary key,
    symbol text,
    date text,
    kind text,
    value real,
    message text,
    created_at text default current_timestamp,
    pushed integer default 0
);

create table if not exists kv (
    key text primary key,
    value text,
    updated_at text default current_timestamp
);

create table if not exists llm_cache (
    key text primary key,
    model text,
    response text,
    in_tokens integer,
    out_tokens integer,
    created_at text default current_timestamp
);

create table if not exists llm_usage (
    model text,
    task text,
    in_tokens integer,
    out_tokens integer,
    cached integer,
    at text default current_timestamp
);
"""


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma journal_mode=wal")
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init():
    with session() as c:
        c.executescript(SCHEMA)


def kv_get(key, default=None):
    with session() as c:
        row = c.execute("select value from kv where key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def kv_set(key, value):
    with session() as c:
        c.execute(
            "insert into kv (key, value) values (?, ?) "
            "on conflict(key) do update set value = excluded.value, updated_at = current_timestamp",
            (key, json.dumps(value, default=str)),
        )


init()
