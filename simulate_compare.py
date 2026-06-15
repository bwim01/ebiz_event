# -*- coding: utf-8 -*-
"""baseline(0609) 대비 크롤·비교 시뮬레이션"""
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
SIM_OUT = ROOT / 'simulation_output'
os.environ['EVENT_OUTPUT_DIR'] = str(SIM_OUT)

import event_db  # noqa: E402
from config import ALERT_PREFIX, CORP, EXCEL_PREFIX  # noqa: E402
from crawl import build_outputs, buho, run_crawl  # noqa: E402

BASELINE_DATE = '20260609'


def seed_baseline_db():
    if SIM_OUT.exists():
        shutil.rmtree(SIM_OUT)
    SIM_OUT.mkdir(parents=True, exist_ok=True)
    baseline = pd.read_excel(ROOT / 'data' / 'baseline.xlsx', sheet_name='전체', engine='openpyxl')
    event_db.save_snapshot(BASELINE_DATE, baseline)
    print(f'[sim] baseline {len(baseline)}건 -> DB {BASELINE_DATE}')


def main():
    print('=' * 60)
    print('baseline 대비 비교 시뮬레이션')
    print('=' * 60)

    seed_baseline_db()
    rows_all, fail = run_crawl()
    new_count = build_outputs(rows_all)

    baseline = event_db._normalize_df(
        pd.read_excel(ROOT / 'data' / 'baseline.xlsx', sheet_name='전체', engine='openpyxl')
    )
    today = rows_all.copy()
    today['제목'] = today['제목'].apply(buho).astype(str).str.strip()
    today['key'] = today['증권사'] + '[]' + today['제목']
    baseline['key'] = baseline['증권사'] + '[]' + baseline['제목'].astype(str)

    dup_keys = today['key'][today['key'].duplicated(keep=False)]
    bad_namu = today[(today['증권사'] == '나무증권') & today['제목'].str.contains('이벤트기간', na=False)]
    namu_new = sorted(
        set(today.loc[today['증권사'] == '나무증권', '제목'])
        - set(baseline.loc[baseline['증권사'] == '나무증권', '제목'])
    )
    namu_missing = sorted(
        set(baseline.loc[baseline['증권사'] == '나무증권', '제목'])
        - set(today.loc[today['증권사'] == '나무증권', '제목'])
    )
    new_keys = sorted(set(today['key']) - set(baseline['key']))
    new_corps = {'대신증권', '신한투자증권', '메리츠증권', '키움증권'}
    unexpected_new = [k for k in new_keys if k.split('[]', 1)[0] not in new_corps]

    today_str = datetime.now(event_db.KST).strftime('%Y%m%d')
    report = SIM_OUT / f'시뮬_리포트_{today_str}.txt'
    lines = [
        f'수집: {len(today)}건 / 신규(알림): {new_count}건 / 크롤 오류 증권사: {fail}개',
        f'중복 key: {len(dup_keys)}건',
        f'나무 잘못된 제목(이벤트기간): {len(bad_namu)}건',
        f'나무 baseline 대비 신규 제목: {len(namu_new)}건',
        f'나무 baseline 대비 누락 제목: {len(namu_missing)}건',
        f'baseline 외 4개사 외 신규: {len(unexpected_new)}건',
        '',
    ]
    if bad_namu.shape[0]:
        lines.append('[나무 잘못된 제목]')
        lines.extend(bad_namu['제목'].tolist())
        lines.append('')
    if namu_new:
        lines.append('[나무 신규 제목]')
        lines.extend(namu_new)
        lines.append('')
    if unexpected_new:
        lines.append('[4개사 외 신규 (baseline 6개사)]')
        lines.extend(unexpected_new[:30])
        if len(unexpected_new) > 30:
            lines.append(f'... 외 {len(unexpected_new) - 30}건')

    report.write_text('\n'.join(lines), encoding='utf-8')
    print('\n' + '-' * 60)
    for line in lines[:6]:
        print(line)
    print(f'\n[sim] 리포트: {report}')
    print(f'[sim] 엑셀: {sorted(SIM_OUT.glob(f"{EXCEL_PREFIX}*.xlsx"))[-1]}')
    alerts = sorted(SIM_OUT.glob(f'{ALERT_PREFIX}*.txt'))
    if alerts:
        print(f'[sim] 알림: {alerts[-1]}')

    ok = (
        len(dup_keys) == 0
        and len(bad_namu) == 0
        and fail == 0
    )
    print('\n결과:', 'PASS' if ok else 'CHECK')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
