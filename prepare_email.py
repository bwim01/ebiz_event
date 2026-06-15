# -*- coding: utf-8 -*-
"""GitHub Actions 메일 본문·첨부 경로 준비"""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config import ALERT_PREFIX, EXCEL_PREFIX, OUTPUT_DIR

KST = ZoneInfo('Asia/Seoul')
now = datetime.now(KST)
subject = f'[경쟁사 이벤트 RPA] {now.month:02d}월 {now.day:02d}일 기준'
Path('/tmp/mail_subject.txt').write_text(subject, encoding='utf-8')

out = OUTPUT_DIR
xlsxs = sorted(out.glob(f'{EXCEL_PREFIX}*.xlsx'))
txts = sorted(out.glob(f'{ALERT_PREFIX}*.txt'))

lines = ['경쟁사 이벤트 크롤링 결과', '']
if txts:
    lines.append(txts[-1].read_text(encoding='utf-8'))
else:
    lines.append('신규 이벤트 없음 (알림 txt 미생성).')

if xlsxs:
    lines.extend(['', f'엑셀: {xlsxs[-1].name}', f'수집 건수 확인용 첨부파일 참고.'])

Path('/tmp/mail_body.txt').write_text('\n'.join(lines), encoding='utf-8')

attachments = []
if xlsxs:
    attachments.append(str(xlsxs[-1]))
if txts:
    attachments.append(str(txts[-1]))

out_attach = Path('/tmp/mail_attachments.txt')
out_attach.write_text('\n'.join(attachments), encoding='utf-8')
print('subject:', subject)
print('body:', '/tmp/mail_body.txt')
print('attachments:', attachments or '(none)')
