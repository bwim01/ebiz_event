# -*- coding: utf-8 -*-
import html
import re
import warnings

import pandas as pd
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from config import COLUMNS, HEADERS

warnings.filterwarnings('ignore')

INIT_SCRIPT = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
SAMSUNG_HOME = 'https://www.samsungpop.com/'
SAMSUNG_EVENT_URL = 'https://www.samsungpop.com/ux/kor/customer/guide/eventguide/event.do'


def _parse_samsung_list(frame, rows):
    name = '삼성증권'
    table = frame.locator('#bodyList1').inner_text().split('자세히보기')
    num = len(table) - 1
    if num <= 0:
        raise RuntimeError('삼성 이벤트 0건')
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
    return num


def _wait_content_frame(page, tries=40):
    for _ in range(tries):
        frame = page.frame(name='content')
        if frame is not None:
            return frame
        page.wait_for_timeout(500)
    return None


def _crawl_samsung(context, rows, stats, errors):
    """삼성은 별도 탭 + frame 직접 이동 (GitHub headless 안정화)."""
    name = '삼성증권'
    page = context.new_page()
    samsung_err = None
    try:
        for attempt in range(3):
            try:
                page.goto(SAMSUNG_HOME, wait_until='load', timeout=90000)
                page.wait_for_timeout(5000)
                frame = _wait_content_frame(page)
                if frame is None:
                    raise RuntimeError('content frame not found')

                loaded = False
                try:
                    frame.goto(SAMSUNG_EVENT_URL, wait_until='domcontentloaded', timeout=90000)
                    page.wait_for_timeout(4000)
                    frame = _wait_content_frame(page)
                    frame.wait_for_selector('#bodyList1 li', timeout=60000)
                    loaded = True
                except Exception as e1:
                    print(f'[삼성] frame.goto 실패, 메뉴 클릭 시도: {e1}')
                    frame = _wait_content_frame(page)
                    frame.evaluate(
                        "document.querySelector('#nav div:nth-child(1) div:nth-child(2) ul li:nth-child(7) a').click()"
                    )
                    page.wait_for_timeout(3000)
                    frame.evaluate(
                        "document.querySelector('#dl_megamenu_M1231757747515 dd:nth-child(3) a').click()"
                    )
                    page.wait_for_timeout(5000)
                    frame = _wait_content_frame(page)
                    frame.wait_for_selector('#bodyList1 li', timeout=60000)
                    loaded = True

                if not loaded or frame is None:
                    raise RuntimeError('삼성 이벤트 페이지 로드 실패')
                num = _parse_samsung_list(frame, rows)
                stats[name] = num
                print(f'[삼성] {num}건 수집')
                return
            except Exception as e:
                samsung_err = e
                print(f'[삼성] 재시도 {attempt + 1}/3: {e}')
                page.wait_for_timeout(3000)
        stats[name] = '오류'
        errors[name] = str(samsung_err)
    finally:
        page.close()


def _parse_kb_date(text):
    text = (text or '').replace('기간', '').replace(' ', '').strip()
    if '~' in text:
        start, end = text.split('~', 1)
        return start.strip(), end.strip()
    return text, ''


def _parse_kb_html(soup, start_no=1):
    name = 'KB증권'
    rows = []
    table = soup.find('ul', attrs={'class': 'eventList'})
    if not table:
        return rows
    items = table.find_all('dl', attrs={'class': 'item'})
    subjs = table.find_all('a', attrs={'class': 'subj'})
    dates = table.find_all('dd', attrs={'class': 'date'})
    for i, subj_el in enumerate(subjs):
        gubun_parts = items[i].get_text().replace('\n', '').split('\xa0') if i < len(items) else ['']
        start, end = _parse_kb_date(dates[i].get_text() if i < len(dates) else '')
        href = subj_el.get('href', '')
        if href and not href.startswith('http'):
            href = 'https://www.kbsec.com' + href
        rows.append({
            '증권사': name, '번호': start_no + i, '구분': gubun_parts[0], 'url': href,
            '제목': subj_el.get_text(), '내용': '', '시작일': start, '종료일': end,
        })
    return rows


_NAMU_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) '
                   'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'),
    'X-Requested-With': 'XMLHttpRequest',
}


def _fmt_dttm(s):
    s = (s or '').strip()
    return f'{s[:4]}/{s[4:6]}/{s[6:8]}' if len(s) == 8 and s.isdigit() else ''


def _crawl_namu_platform(name, list_api, view_tpl):
    """나무/NH 공통 이벤트 목록 JSON API 수집(동일 플랫폼). 제목·기간·상세 URL 포함."""
    resp = requests.get(list_api, headers=_NAMU_HEADERS, params={'pageSize': 100}, timeout=30, verify=False)
    resp.raise_for_status()
    content = (resp.json().get('result') or {}).get('content') or []
    out, seen, idx = [], set(), 0
    for it in content:
        mno = it.get('mNo')
        if mno in seen:
            continue
        seen.add(mno)
        title = (it.get('mTitle') or '').strip()
        if not title:
            continue
        link_url = (it.get('mLinkUrl') or '').strip()
        if it.get('mExposurePage') == 'Y' and link_url:
            url = link_url
        elif mno is not None:
            url = view_tpl.format(mno)
        else:
            url = ''
        idx += 1
        out.append({'증권사': name, '번호': idx, '구분': '', 'url': url, '제목': title,
                    '내용': (it.get('mSummary') or '').strip(),
                    '시작일': _fmt_dttm(it.get('mStartDttm')), '종료일': _fmt_dttm(it.get('mEndDttm'))})
    return out


def crawl_all(page, context=None, skip_samsung=False):
    rows = []
    namu = pd.DataFrame(columns=COLUMNS)
    stats = {}
    errors = {}

    # KB
    name = 'KB증권'
    try:
        url = 'https://www.kbsec.com/go.able?linkcd=m06090002'
        kb_rows = []
        try:
            soup = BeautifulSoup(requests.get(url, headers=HEADERS, verify=False, timeout=20).content, 'html.parser')
            kb_rows = _parse_kb_html(soup)
        except Exception as e:
            print(f'[KB] requests 실패: {e}')

        page.goto(url, wait_until='domcontentloaded', timeout=90000)
        page.wait_for_timeout(2000)
        if not kb_rows:
            kb_rows = _parse_kb_html(BeautifulSoup(page.content(), 'html.parser'))

        try:
            etf_tab = page.locator('xpath=//*[@id="container"]/form/div[2]/a/img')
            if etf_tab.count():
                etf_tab.first.click(timeout=20000)
                page.wait_for_timeout(5000)
                etf_rows = _parse_kb_html(BeautifulSoup(page.content(), 'html.parser'), start_no=len(kb_rows) + 1)
                seen = {r['제목'] for r in kb_rows}
                kb_rows.extend([r for r in etf_rows if r['제목'] not in seen])
        except Exception as e:
            print(f'[KB] ETF 스킵: {e}')

        rows.extend(kb_rows)
        stats[name] = len(kb_rows)
    except Exception as e:
        stats[name] = '오류'
        errors[name] = str(e)

    # NH (목록 JSON API로 수집 → 제목/기간/URL 모두 확보, 브라우저 불필요)
    name = 'NH투자증권'
    try:
        nh_rows = _crawl_namu_platform(
            name,
            'https://m.nhqv.com/customer/event/eventList.json',
            'https://m.nhqv.com/customer/event/eventView?mNo={}',
        )
        rows.extend(nh_rows)
        stats[name] = len(nh_rows)
    except Exception as e:
        stats[name] = '오류'
        errors[name] = str(e)

    # 나무 (목록 JSON API로 수집 → 제목/기간/URL 모두 확보, 브라우저 불필요)
    name = '나무증권'
    try:
        namu_rows = _crawl_namu_platform(
            name,
            'https://m.mynamuh.com/customer/event/eventList.json',
            'https://m.mynamuh.com/customer/event/eventView?mNo={}',
        )
        rows.extend(namu_rows)
        stats[name] = len(namu_rows)
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

    # 삼성 (run_crawl에서 별도 브라우저로 수집)
    if not skip_samsung:
        ctx = context if context is not None else page.context
        _crawl_samsung(ctx, rows, stats, errors)

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

    # 신한 (API로 수집 → url 포함)
    name = '신한투자증권'
    try:
        resp = requests.get(
            'https://bbs2.shinhansec.com/bbs/list/giEvent.do',
            params={'curPage': 1, 'startPage': 1, 'searchText': '7A==', 'searchType': 'VARIABL'},
            headers=HEADERS,
            timeout=30,
            verify=False,
        )
        resp.raise_for_status()
        items = resp.json().get('list', [])
        for i, item in enumerate(items, start=1):
            title = (item.get('f1') or '').strip()
            url = (item.get('f9') or item.get('f2') or '').strip()
            cont = html.unescape(re.sub(r'<[^>]+>', '', item.get('f12') or '')).strip()
            start = (item.get('f6') or '').replace('-', '/')
            end = (item.get('f7') or '').replace('-', '/')
            rows.append({
                '증권사': name, '번호': i, '구분': (item.get('f5') or '').strip(),
                'url': url, '제목': title, '내용': cont, '시작일': start, '종료일': end,
            })
        stats[name] = len(items)
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


