# -*- coding: utf-8 -*-
"""기존 xlsx(전체 시트)를 SQLite에 seed.

사용:
  python seed_db.py [xlsx경로]
  python seed_db.py [xlsx경로] --as-yesterday   # 비교용: 전일 날짜로 저장
  python seed_db.py [xlsx경로] --date 20260609
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

import event_db
from config import OUTPUT_DIR


def _parse_date(path, argv):
    if '--as-yesterday' in argv:
        return (datetime.today() + timedelta(-1)).strftime('%Y%m%d')
    if '--date' in argv:
        i = argv.index('--date')
        return argv[i + 1]
    stem = path.stem
    return stem.split('_')[-1] if '_' in stem else datetime.today().strftime('%Y%m%d')


def seed(path, crawl_date):
    df = pd.read_excel(path, sheet_name='전체', engine='openpyxl')
    event_db.save_snapshot(crawl_date, df)
    print(f'seed OK: {crawl_date} / {len(df)}건 -> {event_db.DB_PATH}')


def main():
    argv = sys.argv[1:]
    flags = {'--as-yesterday', '--date'}
    args = [a for a in argv if a not in flags and not a.startswith('--')]
    if '--date' in argv:
        i = argv.index('--date')
        if i + 1 < len(argv):
            args = [a for a in args if a != argv[i + 1]]

    if args:
        path = Path(args[0])
    else:
        path = OUTPUT_DIR / '경쟁사 이벤트_20260609.xlsx'
    if not path.exists():
        print(f'파일 없음: {path}')
        sys.exit(1)

    date = _parse_date(path, argv)
    seed(path, date)


if __name__ == '__main__':
    main()
