# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from config import COLUMNS, EXCEL_PREFIX, OUTPUT_DIR, ROOT

DB_PATH = OUTPUT_DIR / 'events.db'
BASELINE_XLSX = ROOT / 'data' / 'baseline.xlsx'
KST = ZoneInfo('Asia/Seoul')

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


def _now_kst():
    return datetime.now(KST)


def _today_kst():
    return _now_kst().strftime('%Y%m%d')


def _yesterday_kst():
    return (_now_kst() + timedelta(-1)).strftime('%Y%m%d')


def _apply_buho(text):
    if not isinstance(text, str):
        text = '' if pd.isna(text) else str(text)
    return (text.replace('&#36;', '$').replace('&#37;', '%').replace('&#38;', '&')
            .replace('&#162;', '¢').replace('&#163;', '£').replace('&#165;', '¥')
            .replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
            .replace('&quot;', '"').replace('&#35;', '#').replace('&#39;', "'"))


def _normalize_df(df):
    if df is None or df.empty:
        return _empty_df()
    out = df.copy()
    for col in COLUMNS:
        if col not in out.columns:
            out[col] = ''
    out = out[COLUMNS].fillna('')
    out['증권사'] = out['증권사'].astype(str).str.strip()
    out['제목'] = out['제목'].astype(str).map(_apply_buho).str.strip()
    return out


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


def _load_latest_db_before(today):
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        dates = pd.read_sql_query('SELECT DISTINCT crawl_date FROM events WHERE crawl_date < ? ORDER BY crawl_date DESC LIMIT 1', conn, params=(today,))
        if dates.empty:
            return _empty_df(), ''
        crawl_date = dates.iloc[0, 0]
        df = pd.read_sql_query(
            f'SELECT {", ".join(COLUMNS)} FROM events WHERE crawl_date = ?',
            conn,
            params=(crawl_date,),
        )
        return df, crawl_date


def load_yesterday():
    """전일(KST) DB → 최근 DB → 전일 xlsx → baseline xlsx 순으로 비교 기준 로드."""
    today = _today_kst()
    yesterday = _yesterday_kst()

    df = _load_from_db(yesterday)
    if not df.empty:
        print(f'[DB] 비교 기준: 전일 DB {yesterday} / {len(df)}건')
        return _normalize_df(df)

    df, crawl_date = _load_latest_db_before(today)
    if not df.empty:
        print(f'[DB] 비교 기준: 최근 DB {crawl_date} / {len(df)}건')
        return _normalize_df(df)

    df = _load_xlsx_fallback(yesterday)
    if not df.empty:
        save_snapshot(yesterday, df)
        print(f'[DB] 비교 기준: 전일 xlsx {yesterday} / {len(df)}건')
        return _normalize_df(df)

    df = _load_baseline_xlsx()
    print(f'[DB] 비교 기준: baseline xlsx / {len(df)}건')
    return _normalize_df(df)


def load_compare_baseline():
    """비교용 기준 = 원본 baseline.xlsx (0609, 94건) 고정."""
    df = _load_baseline_xlsx()
    print(f'[DB] 비교 기준: 원본 baseline / {len(df)}건')
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
