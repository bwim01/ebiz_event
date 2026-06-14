# -*- coding: utf-8 -*-
"""GitHub Actions 메일 본문·첨부 경로 준비"""
from pathlib import Path

from config import ALERT_PREFIX, EXCEL_PREFIX, OUTPUT_DIR

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
print('body:', '/tmp/mail_body.txt')
print('attachments:', attachments or '(none)')
