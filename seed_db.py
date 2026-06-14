# -*- coding: utf-8 -*-
"""기존 xlsx(전체 시트)를 SQLite에 seed. 사용: python seed_db.py [xlsx경로]"""
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

import event_db
from config import OUTPUT_DIR

def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        path = OUTPUT_DIR / '경쟁사 이벤트_20260609.xlsx'
    if not path.exists():
        print(f'파일 없음: {path}')
        sys.exit(1)
    df = pd.read_excel(path, sheet_name='전체', engine='openpyxl')
    # 파일명에서 날짜 추출 (경쟁사 이벤트_YYYYMMDD.xlsx)
    stem = path.stem
    date = stem.split('_')[-1] if '_' in stem else datetime.today().strftime('%Y%m%d')
    event_db.save_snapshot(date, df)
    print(f'seed OK: {date} / {len(df)}건 -> {event_db.DB_PATH}')

if __name__ == '__main__':
    main()
