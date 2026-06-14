# -*- coding: utf-8 -*-
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = Path(os.environ.get('EVENT_OUTPUT_DIR', ROOT / 'output'))

EXCEL_PREFIX = '경쟁사 이벤트_'
ALERT_PREFIX = '경쟁사 신규 이벤트 업로드 알림_'

COLUMNS = ['증권사', '번호', '구분', 'url', '제목', '내용', '시작일', '종료일']
CORP = [
    'KB증권', 'NH투자증권', '미래에셋증권', '삼성증권', '키움증권', '한국투자증권', '나무증권',
    '대신증권', '신한투자증권', '메리츠증권',
]
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
