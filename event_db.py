# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime, timedelta

import pandas as pd

from config import COLUMNS, EXCEL_PREFIX, OUTPUT_DIR, ROOT

DB_PATH = OUTPUT_DIR / 'events.db'
BASELINE_XLSX = ROOT / 'data' / '경쟁사 이벤트_20260609.xlsx'

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crawl_date TEXT NOT NULL,
    증권사 TEXT,
    번호 INTEGER,
    구분 TEXT,
    url TEXT,
    제목 TEXT,
    내용 TEXT,
    시작일 TEXT,
    종료일 TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_crawl_date ON events(crawl_date);
"""


def init_db():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(_CREATE_SQL)


def _empty_df():
    return pd.DataFrame(columns=COLUMNS)


def _normalize_df(df):
    if df is None or df.empty:
        return _empty_df()
    out = df.copy()
    for col in COLUMNS:
        if col not in out.columns:
            out[col] = ''
    return out[COLUMNS].fillna('')


def _load_from_db(crawl_date):
    init_db()
    query = f'SELECT {", ".join(COLUMNS)} FROM events WHERE crawl_date = ?'
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(query, conn, params=(crawl_date,))


def _load_xlsx_fallback(crawl_date):
    path = OUTPUT_DIR / f'{EXCEL_PREFIX}{crawl_date}.xlsx'
    if not path.exists():
        return _empty_df()
    try:
        return pd.read_excel(path, sheet_name='전체', engine='openpyxl')
    except Exception:
        return _empty_df()


def _load_baseline_xlsx():
    if not BASELINE_XLSX.exists():
        return _empty_df()
    try:
        return pd.read_excel(BASELINE_XLSX, sheet_name='전체', engine='openpyxl')
    except Exception:
        return _empty_df()


def load_yesterday():
    """전일 DB → 전일 xlsx → data/경쟁사 이벤트_20260609.xlsx 순으로 비교 기준 로드."""
    yesterday = (datetime.today() + timedelta(-1)).strftime('%Y%m%d')
    df = _load_from_db(yesterday)
    if not df.empty:
        return _normalize_df(df)
    df = _load_xlsx_fallback(yesterday)
    if not df.empty:
        save_snapshot(yesterday, df)
        return _normalize_df(df)
    df = _load_baseline_xlsx()
    return _normalize_df(df)


def save_snapshot(crawl_date, df):
    df = _normalize_df(df)
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('DELETE FROM events WHERE crawl_date = ?', (crawl_date,))
        conn.executemany(
            f'INSERT INTO events (crawl_date, {", ".join(COLUMNS)}) VALUES (?, {", ".join("?" * len(COLUMNS))})',
            [(crawl_date, *row) for row in df.itertuples(index=False, name=None)],
        )
        conn.commit()
