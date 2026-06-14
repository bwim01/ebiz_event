# -*- coding: utf-8 -*-
import re
import warnings
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from config import COLUMNS, HEADERS

warnings.filterwarnings('ignore')

def crawl_all(page):
    rows = []
    namu = pd.DataFrame(columns=COLUMNS)
    stats = {}
    errors = {}

    # KB
    name = 'KB증권'
    try:
        url = 'https://www.kbsec.com/go.able?linkcd=m06090002'
        soup = BeautifulSoup(requests.get(url, headers=HEADERS, verify=False, timeout=20).content, 'html.parser')
        table = soup.find('ul', attrs={'class': 'eventList'})
        base_count = 0
        if table:
            num = len(table.find_all('a', attrs={'class': 'subj'}))
            base_count = num
            for i in range(num):
                gubun = table.find_all('dl', attrs={'class': 'item'})[i].get_text().replace('\n', '').split('\xa0')
                subj = table.find_all('a', attrs={'class': 'subj'})[i].get_text()
                date = table.find_all('dd', attrs={'class': 'date'})[i].get_text().replace('기간', '').replace(' ', '').split('~')
                href = 'https://www.kbsec.com' + table.find_all('a', attrs={'class': 'subj'})[i]['href']
                rows.append({'증권사': name, '번호': i + 1, '구분': gubun[0], 'url': href, '제목': subj,
                             '내용': '', '시작일': date[0], '종료일': date[1]})
        page.goto(url, wait_until='networkidle', timeout=90000)
        etf_tab = page.locator('xpath=//*[@id="container"]/form/div[2]/a/img')
        etf_tab.first.wait_for(state='visible', timeout=20000)
        etf_tab.first.click(timeout=20000)
        page.wait_for_selector('xpath=//*[@id="container"]/form/div[3]/ul', timeout=20000)
        table_txt = page.locator('xpath=//*[@id="container"]/form/div[3]/ul').first.inner_text().split('\n')
        num = int(len(table_txt) / 3)
        for k in range(num):
            gubun = table_txt[3 * k]
            subj = table_txt[3 * k + 1]
            date = table_txt[3 * k + 2].replace('기간', '').replace(' ', '').split('~')
            href = page.locator(f'xpath=//*[@id="container"]/form/div[3]/ul/li[{k + 1}]/dl/dt/a').first.get_attribute('href')
            rows.append({'증권사': name, '번호': base_count + k + 1, '구분': gubun, 'url': href, '제목': subj,
                         '내용': '', '시작일': date[0], '종료일': date[1]})
        stats[name] = len([r for r in rows if r['증권사'] == name])
    except Exception as e:
        stats[name] = '오류'
        errors[name] = str(e)

    # NH
    name = 'NH투자증권'
    try:
        page.goto('https://www.nhqv.com/', wait_until='networkidle', timeout=90000)
        frame = page.frame_locator('#iflg_body')
        frame.locator('xpath=//*[@id="gnvVID"]/li[6]/a').click(timeout=20000)
        frame.locator('xpath=//*[@id="menu_524"]').first.click(timeout=20000)
        frame.locator('xpath=//*[@id="menu_540"]/span').first.click(timeout=20000)
        frame.locator('xpath=//*[@id="rowCount"]').select_option('30')
        frame.locator('xpath=//*[@id="contents"]/form/div/div[2]/div/div/a').click(timeout=20000)
        frame.locator('xpath=//*[@id="contents"]/ul').wait_for(timeout=20000)
        table = frame.locator('xpath=//*[@id="contents"]/ul').inner_text().split('\n')
        num = int(len(table) / 4)
        for i in range(num):
            date = table[4 * i + 2].replace('이벤트기간 : ', '').replace(' ', '').replace('.', '/').split('~')
            rows.append({'증권사': name, '번호': i + 1, '구분': '', 'url': '', '제목': table[4 * i],
                         '내용': table[4 * i + 1], '시작일': date[0], '종료일': date[1]})
        stats[name] = num
    except Exception as e:
        stats[name] = '오류'
        errors[name] = str(e)

    # 나무
    name = '나무증권'
    try:
        list_url = 'https://m.mynamuh.com/customer/event/eventList'

        def format_date(date_str):
            try:
                return datetime.strptime(date_str, '%Y.%m.%d').strftime('%Y/%m/%d')
            except ValueError:
                return '날짜 없음'

        page.goto(list_url, wait_until='domcontentloaded', timeout=60000)
        page.wait_for_selector('#ulList1', timeout=15000)
        lines = page.locator('#ulList1').inner_text().split('\n')
        events, links = [], []
        for i in range(0, len(lines) - 1, 2):
            title = lines[i].strip()
            period = lines[i + 1].replace('이벤트기간 : ', '').strip()
            if ' ~ ' in period:
                start_date, end_date = period.split(' ~ ')
                start_date, end_date = format_date(start_date), format_date(end_date)
            else:
                start_date, end_date = format_date(period), '날짜 없음'
            events.append([title, start_date, end_date])
        idx = 1
        while True:
            xpath = f'xpath=//*[@id="ulList1"]/li[{idx}]/a'
            try:
                link = page.locator(xpath)
                link.wait_for(state='attached', timeout=5000)
                text = link.inner_text().strip()
                if text == '더보기':
                    break
                link.click(timeout=10000)
                page.wait_for_load_state('domcontentloaded', timeout=15000)
                links.append(page.url)
                page.goto(list_url, wait_until='domcontentloaded', timeout=60000)
                page.wait_for_selector('#ulList1', timeout=15000)
                idx += 1
            except PlaywrightTimeout:
                break
        namu = (pd.DataFrame(events, columns=['제목', '시작일', '종료일'])
                .query("제목 != '더보기'").reset_index(drop=True))
        if len(links) < len(namu):
            links = links + [''] * (len(namu) - len(links))
        else:
            links = links[:len(namu)]
        namu = (namu.assign(증권사=name, 번호=lambda x: x.index + 1, 구분='', 내용='', url=links)
                .filter(items=COLUMNS))
        stats[name] = len(namu)
    except Exception as e:
        stats[name] = '오류'
        errors[name] = str(e)

    # 미래에셋
    name = '미래에셋증권'
    try:
        j, cnt = 1, 1
        while cnt != 0:
            url = f'https://securities.miraeasset.com/hki/hki7000/r05.do?currentPage={j}&cs_ecis_id=#'
            soup = BeautifulSoup(requests.get(url, verify=False, timeout=20).content, 'html.parser')
            cnt = len(soup.find_all('dd', attrs={'class': 'evTit'}))
            for i in range(cnt):
                subj = soup.find_all('dd', attrs={'class': 'evTit'})[i].get_text()
                date = soup.find_all('dd', attrs={'class': 'evDate'})[i].get_text().replace('.', '/').replace(' ', '').split('~')
                juso = soup.find_all('dl', attrs={'class': 'eventCont'})[i].find('a')['href'].replace('javascript:doView(', '').replace("'", '').replace(')', '').split(',')
                eid, sect, eurl = juso[0], juso[1], juso[2]
                href = ('https://securities.miraeasset.com' + eurl if sect == '2'
                        else f'https://securities.miraeasset.com/hki/hki7000/v05.do?cs_ecis_id={eid}&strEnd=S')
                rows.append({'증권사': name, '번호': 9 * (j - 1) + i + 1, '구분': '', 'url': href, '제목': subj,
                             '내용': '', '시작일': date[0], '종료일': date[1]})
            j += 1
        stats[name] = len([r for r in rows if r['증권사'] == name])
    except Exception as e:
        stats[name] = '오류'
        errors[name] = str(e)

    # 삼성 (content frame → 메뉴 클릭, hover 없이 진행)
    name = '삼성증권'
    try:
        page.goto('https://www.samsungpop.com/', wait_until='domcontentloaded', timeout=90000)
        frame = page.frame(name='content')
        if frame is None:
            raise RuntimeError('content frame not found')
        frame.locator('#nav div:nth-child(1) div:nth-child(2) ul li:nth-child(7) a').first.click(timeout=30000)
        page.wait_for_timeout(2000)
        frame.locator('#dl_megamenu_M1231757747515 dd:nth-child(3) a').first.click(timeout=30000)
        page.wait_for_timeout(4000)
        frame = page.frame(name='content')
        if frame is None:
            raise RuntimeError('content frame lost after menu click')
        frame.wait_for_selector('#bodyList1 li', timeout=45000)
        table = frame.locator('#bodyList1').inner_text().split('자세히보기')
        num = len(table) - 1
        for i in range(num):
            value = [x for x in table[i].split('\n') if x]
            if value[-1].startswith('종료') or value[-1].startswith('오늘'):
                value.pop()
            subj = value[0]
            cont = value[1] if len(value) == 3 else ''
            date = value[-1].replace('-', '/').replace(' ', '').split('~')
            juso = frame.locator(f'#bodyList1 li:nth-child({i + 1}) a').first.get_attribute('href')
            juso = (juso or '').replace('javascript:goIngView(', '').replace("'", '').replace(');', '')
            href = f'https://www.samsungpop.com/customer/guide.do?cmd=event_view&menuNo=01010900&MenuSeqNo={juso}'
            rows.append({'증권사': name, '번호': i + 1, '구분': '', 'url': href, '제목': subj, '내용': cont,
                         '시작일': date[0], '종료일': date[1]})
        stats[name] = num
    except Exception as e:
        stats[name] = '오류'
        errors[name] = str(e)

    # 키움
    name = '키움증권'
    try:
        page.goto('https://www.kiwoom.com/e/common/event/VIngEventView?tp=', wait_until='networkidle', timeout=90000)
        if '/error' in page.url:
            raise RuntimeError(f'키움 접근 차단: {page.url}')
        page.wait_for_selector('#evtBannerList [evnt_cd]', timeout=45000)
        date_re = re.compile(r'(\d{4})\.(\d{2})\.(\d{2})\s*~\s*(\d{4})\.(\d{2})\.(\d{2})')
        idx = 0
        items = page.locator('#evtBannerList [evnt_cd]').all()
        for item in items:
            evnt_cd = item.get_attribute('evnt_cd') or ''
            if len(evnt_cd) <= 4:
                continue
            gubun = item.get_attribute('evnt_tp') or ''
            subj = ''
            for img in item.locator('img[alt]').all():
                alt = (img.get_attribute('alt') or '').strip()
                if alt and alt != '키움증권':
                    subj = alt
                    break
            if not subj:
                lines = [x.strip() for x in item.inner_text().split('\n') if x.strip()]
                subj = lines[0] if lines else ''
            period = ''
            for el in item.locator('[id="evtPeriod"]').all():
                period = el.inner_text().strip()
                if period:
                    break
            if period:
                parts = period.split('~')
                start = parts[0].strip().replace('.', '/')
                end = parts[1].strip().replace('.', '/') if len(parts) > 1 else ''
            else:
                m = date_re.search(item.inner_text())
                start = f"{m.group(1)}/{m.group(2)}/{m.group(3)}" if m else ''
                end = f"{m.group(4)}/{m.group(5)}/{m.group(6)}" if m else ''
            idx += 1
            rows.append({
                '증권사': name, '번호': idx, '구분': gubun,
                'url': f'https://www1.kiwoom.com/h/common/event/VEventMainView?eventCode={evnt_cd}',
                '제목': subj, '내용': '', '시작일': start, '종료일': end,
            })
        stats[name] = idx
    except Exception as e:
        stats[name] = '오류'
        errors[name] = str(e)

    # 한국투자
    name = '한국투자증권'
    try:
        j, cnt = 1, 1
        while cnt != 0:
            url = ('https://securities.koreainvestment.com/main/customer/notice/Event.jsp?gubun=i&cmd=TF04gb010001'
                   f'&num=&from=&currentPage={j}&CUSTGUBUN=00&focusYN=&userRowsPerPage=10&searchColumn=all&searchValue=')
            soup = BeautifulSoup(requests.get(url, headers=HEADERS, verify=False, timeout=20).content, 'html.parser')
            cnt = len(soup.find_all('p', attrs={'class': 'title'}))
            for i in range(cnt):
                gubun = soup.find_all('span', attrs={'class': 'event_ing'})[i].get_text()
                subj = soup.find_all('p', attrs={'class': 'title'})[i].get_text()
                cont = soup.find_all('p', attrs={'class': 'con'})[i].get_text()
                date = soup.find_all('p', attrs={'class': 'date'})[i].get_text().replace('\n', '').replace('\t', '').replace('기간 :', '').replace('.', '/').split('~')
                juso = soup.find_all('a', attrs={'class': 'event_thum_box'})[i]['href'].replace('javascript:doView(', '').replace("'", '').replace(')', '').replace(';', '')
                href = ('https://securities.koreainvestment.com/main/customer/notice/Event.jsp?gubun=i&cmd=TF04gb010002'
                        f'&num={juso}&from=&currentPage=1&CUSTGUBUN=00&focusYN=&userRowsPerPage=10&searchColumn=all&searchValue=')
                rows.append({'증권사': name, '번호': 10 * (j - 1) + i + 1, '구분': gubun, 'url': href, '제목': subj,
                             '내용': cont, '시작일': date[0], '종료일': date[1].split('종료')[0]})
            j += 1
        stats[name] = len([r for r in rows if r['증권사'] == name])
    except Exception as e:
        stats[name] = '오류'
        errors[name] = str(e)

    # 대신
    name = '대신증권'
    try:
        soup = BeautifulSoup(requests.get('https://www.daishin.com/g.ds?m=1109&p=12931&v=12831', headers=HEADERS, verify=False, timeout=20).content, 'html.parser')
        for i, box in enumerate(soup.select('div.eventBox')):
            tit_el = box.select_one('p.tit a')
            term_el = box.select_one('p.term')
            if not tit_el:
                continue
            term_text = term_el.get_text(' ', strip=True).split('조회수')[0].strip() if term_el else ''
            date = term_text.replace('.', '/').replace(' ', '').split('~')
            href_path = tit_el.get('href', '')
            rows.append({'증권사': name, '번호': i + 1, '구분': '',
                         'url': 'https://www.daishin.com' + href_path if href_path.startswith('/') else href_path,
                         '제목': tit_el.get_text(strip=True),
                         '내용': box.select_one('p.sub').get_text(strip=True) if box.select_one('p.sub') else '',
                         '시작일': date[0].strip(), '종료일': date[1].strip() if len(date) > 1 else ''})
        stats[name] = len([r for r in rows if r['증권사'] == name])
    except Exception as e:
        stats[name] = '오류'
        errors[name] = str(e)

    # 신한
    name = '신한투자증권'
    try:
        page.goto('https://www.shinhansec.com/siw/customer-center/event/giEvent1/view.do', wait_until='networkidle', timeout=90000)
        page.wait_for_timeout(3000)
        date_re = re.compile(r'(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\s*~\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})')
        for _ in range(20):
            btns = page.locator('a:has-text("더보기")')
            if btns.count() == 0:
                break
            btns.first.click(timeout=10000)
            page.wait_for_timeout(1500)
        idx = 0
        event_items = [el for el in page.locator('ul.list > li').all()
                       if date_re.search(el.inner_text())]
        for item in event_items:
            text = item.inner_text().strip()
            m = date_re.search(text)
            if not m:
                continue
            lines = [x.strip() for x in text.split('\n') if x.strip()]
            cont = next((ln for ln in lines[1:] if not date_re.search(ln) and ln != '자세히 보기' and '신한투자증권' not in ln), '')
            idx += 1
            rows.append({'증권사': name, '번호': idx, '구분': '', 'url': '', '제목': lines[0], '내용': cont,
                         '시작일': f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}",
                         '종료일': f"{m.group(4)}/{int(m.group(5)):02d}/{int(m.group(6)):02d}"})
        stats[name] = idx
    except Exception as e:
        stats[name] = '오류'
        errors[name] = str(e)

    # 메리츠
    name = '메리츠증권'
    try:
        last_err = None
        data = None
        for _ in range(3):
            try:
                resp = requests.get('https://home.imeritz.com/cust/ntcevnt/PrgsEvntList.do', headers=HEADERS, verify=False, timeout=30)
                data = resp.json()
                break
            except Exception as e:
                last_err = e
                page.wait_for_timeout(2000)
        if data is None:
            raise last_err
        for i, item in enumerate(data.get('selectList', [])):
            start_raw, end_raw = item.get('evntStartDate', ''), item.get('evntEndDate', '')
            start = f"{start_raw[:4]}/{start_raw[4:6]}/{start_raw[6:8]}" if len(start_raw) == 8 else start_raw
            end = f"{end_raw[:4]}/{end_raw[4:6]}/{end_raw[6:8]}" if len(end_raw) == 8 else end_raw
            img = item.get('evntDescImg', '')
            rows.append({'증권사': name, '번호': i + 1, '구분': '',
                         'url': f'https://home.imeritz.com/cust/ntcevnt/{img}' if img else '',
                         '제목': item.get('evntTitle', ''),
                         '내용': re.sub(r'<[^>]+>', '', item.get('evntDesc', '')).strip(),
                         '시작일': start, '종료일': end})
        stats[name] = len(data.get('selectList', []))
    except Exception as e:
        stats[name] = '오류'
        errors[name] = str(e)

    return rows, namu, stats, errors


