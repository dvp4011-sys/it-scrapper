"""Scrape public HTML, rank JobPosting data, append new matches to Sheets."""
import argparse
import csv
import json
import logging
import os
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from candidate_profile import PROFILE_HEADERS, default_rows, parse_profile, rank_keywords

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HEADERS = ['Dodano','Firma','Stanowisko','Link','Status','Wysłano CV','Rozmowa','Następny krok','Termin','Match','Widełki / forma','Kontakt','Luki','Dopisz do CV','Notatki','Źródło','Uzasadnienie','Lokalizacja','Data publikacji']
AGENT = 'ITJobScraper/0.1'
LOG = logging.getLogger(__name__)


def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value).lower()) if not unicodedata.combining(c)).replace('ł','l')


def canonical(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip('/'), '', ''))


def text(value):
    return BeautifulSoup(str(value or ''), 'html.parser').get_text(' ', strip=True)


class Fetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers['User-Agent'] = AGENT
        retry = Retry(total=2, backoff_factor=2, status_forcelist=[429,500,502,503,504])
        self.session.mount('https://', HTTPAdapter(max_retries=retry))
        self.robots = {}
        self.last_request = 0

    def request(self, url):
        time.sleep(max(0, 1.5 - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        response = self.session.get(url, timeout=35, allow_redirects=False)
        response.raise_for_status()
        if 300 <= response.status_code < 400:
            raise RuntimeError('Przekierowanie do sprawdzenia: ' + url)
        return response

    def get(self, url):
        p = urlsplit(url)
        origin = f'{p.scheme}://{p.netloc}'
        if origin not in self.robots:
            robot = RobotFileParser()
            response = self.request(origin + '/robots.txt')
            robot.parse(response.text.lstrip('\ufeff').splitlines())
            self.robots[origin] = robot
        if not self.robots[origin].can_fetch(AGENT, url):
            raise RuntimeError('robots.txt nie zezwala: ' + url)
        return self.request(url).text


def postings(html):
    def walk(obj):
        if isinstance(obj, list):
            for item in obj:
                yield from walk(item)
        elif isinstance(obj, dict):
            kind = obj.get('@type', [])
            if kind == 'JobPosting' or isinstance(kind, list) and 'JobPosting' in kind:
                yield obj
            for value in obj.values():
                if isinstance(value, (dict, list)):
                    yield from walk(value)
    for script in BeautifulSoup(html, 'html.parser').select('script[type="application/ld+json"]'):
        try:
            yield from walk(json.loads(script.string or script.get_text()))
        except (ValueError, TypeError):
            LOG.warning('Nieprawidłowy JSON-LD')


def parse_offer(data, url, source):
    locations = data.get('jobLocation') or []
    if isinstance(locations, dict):
        locations = [locations]
    cities = [x['address'].get('addressLocality','') for x in locations if isinstance(x,dict) and isinstance(x.get('address'),dict)]
    salary = data.get('baseSalary') or {}
    salary = salary if isinstance(salary,dict) else {}
    value = salary.get('value') or {}
    value = value if isinstance(value,dict) else {'value':value}
    org = data.get('hiringOrganization') or {}
    return dict(url=canonical(url), source=source, title=text(data.get('title')), company=text(org.get('name','') if isinstance(org,dict) else org), description=text(data.get('description')), cities=cities, remote=data.get('jobLocationType') == 'TELECOMMUTE', salary=salary, value=value, employment=data.get('employmentType',''), published=data.get('datePosted',''), expiry=data.get('validThrough',''))


def evaluate(job, profile):
    title, body = norm(job['title']), norm(job['description'])
    combined = title + ' ' + body
    if job['expiry']:
        try:
            dt = datetime.fromisoformat(job['expiry'].replace('Z','+00:00'))
            if dt.replace(tzinfo=dt.tzinfo or timezone.utc) < datetime.now(timezone.utc):
                return None
        except ValueError:
            pass
    ranked = rank_keywords(job['title'], job['description'], profile) if 'rules' in profile else None
    if 'rules' in profile and ranked is None:
        return None
    if 'rules' not in profile and not any(k in title for k in ['android','xamarin','mobile','maui','pos','payment','platnos']) and 'xamarin' not in body:
        return None
    local = any(norm(target.strip()) in norm(city) for target in profile['city'].split('|') if target.strip() for city in job['cities'])
    if not local and not (profile['remote'] and job['remote']):
        return None
    if 'rules' in profile:
        score, reasons, gaps = ranked
    else:
        score, reasons = 0, []
        for label, found, points in [
            ('Xamarin','xamarin' in combined,40),
            ('Android','android' in combined,25),
            ('Android + Java','android' in combined and bool(re.search(r'\bjava\b',combined)),15),
            ('PAX',bool(re.search(r'\bpax\b',combined)),15),
            ('POS / terminale',bool(re.search(r'\bpos\b|terminal',combined)),10),
            ('Płatności',any(k in combined for k in ['payment','platnos','card acquiring']),5),
            ('Drukarki',any(k in combined for k in ['printer','drukark']),5),
        ]:
            if found:
                score += points
                reasons.append(label)
    val, salary = job['value'], job['salary']
    unit = str(val.get('unitText','')).upper()
    upper = val.get('maxValue',val.get('value'))
    factor = {'MONTH':1,'HOUR':profile['hourly_month_hours'],'YEAR':1/12}.get(unit)
    known = isinstance(upper,(int,float)) and salary.get('currency') == 'PLN' and factor is not None
    if known and upper * factor < profile['minimum_monthly_pln']:
        return None
    reasons.append('Miasto: '+profile['city'] if local else 'Zdalnie: sprawdź kraj i wizyty w biurze')
    if not known:
        reasons.append('Płaca do weryfikacji')
    elif unit == 'HOUR':
        reasons.append(f"Przeliczenie płacy: {profile['hourly_month_hours']} h/mies.")
    if not known and not profile.get('keep_unknown_salary', True):
        return None
    if 'rules' not in profile:
        gaps = [skill + ' — do potwierdzenia' for skill in profile['unconfirmed'] if norm(skill) in combined]
    if score < profile['minimum_score']:
        return None
    return {'score':min(round(score),95),'reasons':'; '.join(reasons),'gaps':'; '.join(gaps)}


def make_row(job, match):
    val = job['value']
    amount = f"{val.get('minValue',val.get('value','?'))}–{val.get('maxValue',val.get('value','?'))} {job['salary'].get('currency','')} / {val.get('unitText','?')}" if job['salary'] else 'brak widełek'
    return [datetime.now(timezone.utc).date().isoformat(),job['company'],job['title'],job['url'],'Do sprawdzenia','','','','',f"{match['score']}%",f"{amount}; {job['employment']}",'',match['gaps'],'','',job['source'],match['reasons'],', '.join(job['cities']) + (' / zdalnie' if job['remote'] else ''),job['published']]


class Sheets:
    def __init__(self, sheet_id):
        import google.auth
        from googleapiclient.discovery import build
        credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/spreadsheets'])
        self.api = build('sheets','v4',credentials=credentials,cache_discovery=False).spreadsheets()
        self.id = sheet_id
        tabs = self.api.get(spreadsheetId=self.id).execute()['sheets']
        titles = {tab['properties']['title'] for tab in tabs}
        operations = [{'addSheet':{'properties':{'title':title,'gridProperties':{'frozenRowCount':1}}}} for title in ['Oferty','Historia uruchomień'] if title not in titles]
        if operations:
            self.api.batchUpdate(spreadsheetId=self.id,body={'requests':operations}).execute()
        for title, header in [('Oferty',HEADERS),('Historia uruchomień',['Czas UTC','Źródło','Status','Szczegóły'])]:
            existing = self.read(f"'{title}'!A1:S1")
            if not existing:
                self.append(title,[header])
            elif existing[0] != header:
                raise RuntimeError('Niezgodny nagłówek: ' + title + '. Zapis zatrzymany dla ochrony danych.')

    def load_profile(self):
        tabs = self.api.get(spreadsheetId=self.id).execute()['sheets']
        matches = [tab['properties'] for tab in tabs if tab['properties']['title'] == 'Profil']
        if not matches:
            response = self.api.batchUpdate(spreadsheetId=self.id,body={'requests':[{'addSheet':{'properties':{'title':'Profil','gridProperties':{'frozenRowCount':1}}}}]}).execute()
            sheet_id = response['replies'][0]['addSheet']['properties']['sheetId']
            rows = default_rows()
            self.append('Profil',rows)
            requests_ = [
                {'repeatCell':{'range':{'sheetId':sheet_id,'startRowIndex':0,'endRowIndex':1},'cell':{'userEnteredFormat':{'backgroundColor':{'red':0.12,'green':0.28,'blue':0.43},'textFormat':{'bold':True,'foregroundColor':{'red':1,'green':1,'blue':1}},'wrapStrategy':'WRAP'}},'fields':'userEnteredFormat'}},
                {'repeatCell':{'range':{'sheetId':sheet_id,'startRowIndex':1,'startColumnIndex':0,'endColumnIndex':10},'cell':{'userEnteredFormat':{'verticalAlignment':'TOP','wrapStrategy':'WRAP'}},'fields':'userEnteredFormat'}},
                {'updateDimensionProperties':{'range':{'sheetId':sheet_id,'dimension':'COLUMNS','startIndex':0,'endIndex':10},'properties':{'pixelSize':140},'fields':'pixelSize'}},
                {'updateDimensionProperties':{'range':{'sheetId':sheet_id,'dimension':'COLUMNS','startIndex':1,'endIndex':3},'properties':{'pixelSize':230},'fields':'pixelSize'}},
                {'updateDimensionProperties':{'range':{'sheetId':sheet_id,'dimension':'COLUMNS','startIndex':9,'endIndex':10},'properties':{'pixelSize':520},'fields':'pixelSize'}},
                {'setBasicFilter':{'filter':{'range':{'sheetId':sheet_id,'startRowIndex':0,'endRowIndex':len(rows),'startColumnIndex':0,'endColumnIndex':10}}}},
            ]
            for col, choices in [(0,['ustawienie','rola','skill','własne','instrukcja']),(7,['TAK','NIE']),(8,['tytuł','całość'])]:
                requests_.append({'setDataValidation':{'range':{'sheetId':sheet_id,'startRowIndex':1,'startColumnIndex':col,'endColumnIndex':col+1},'rule':{'condition':{'type':'ONE_OF_LIST','values':[{'userEnteredValue':v} for v in choices]},'strict':True,'showCustomUi':True}}})
            self.api.batchUpdate(spreadsheetId=self.id,body={'requests':requests_}).execute()
            LOG.info('Utworzono kartę Profil; kolejne uruchomienia zachowają edycje użytkownika')
        return parse_profile(self.read("'Profil'!A:J"))

    def read(self, range_):
        return self.api.values().get(spreadsheetId=self.id,range=range_).execute().get('values',[])

    def known(self):
        return {canonical(r[0]) for r in self.read("'Oferty'!D2:D") if r and r[0]}

    def append(self, title, rows):
        if rows:
            self.api.values().append(spreadsheetId=self.id,range=f"'{title}'!A1",valueInputOption='RAW',insertDataOption='INSERT_ROWS',body={'values':rows}).execute()



def offer_links(soup, page, source):
    links = [canonical(urljoin(page,a['href'])) for a in soup.select('a[href]') if source['pattern'] in a['href']]
    listing_urls = {canonical(p) for p in source['pages']}
    links = [u for u in links if urlsplit(u).netloc == urlsplit(page).netloc and u not in listing_urls]
    if source['name'] == 'pracuj':
        links = [u for u in links if ',oferta,' in u]
    return links

def run(args):
    sources = json.loads(Path(args.sources).read_text(encoding='utf-8-sig'))
    use_sheet_profile = args.profile_source == 'sheets' or args.profile_source == 'auto' and args.write_sheets
    sheet = Sheets(os.environ['GOOGLE_SHEET_ID']) if args.write_sheets or use_sheet_profile or args.init_profile_only else None
    profile = sheet.load_profile() if use_sheet_profile or args.init_profile_only else json.loads(Path(args.profile).read_text(encoding='utf-8-sig'))
    LOG.info('Profil z %s: aktywne skille=%s, role=%s', 'Google Sheets' if use_sheet_profile else args.profile, len(profile.get('rules', [])),len(profile.get('roles', [])))
    if args.init_profile_only:
        LOG.info('Karta Profil poprawnie zapisana i odczytana. Bez pobierania ofert.')
        return 0
    known = sheet.known() if sheet and args.write_sheets else set()
    fetcher, rows, history = Fetcher(), [], []
    failures = 0
    for source in sources:
        if not source['enabled']:
            continue
        errors, urls, parsed = [], [], 0
        for page in source['pages']:
            try:
                soup = BeautifulSoup(fetcher.get(page),'html.parser')
                links = offer_links(soup, page, source)
                if not links:
                    raise RuntimeError('Brak ofert w HTML: zmiana strony lub wymagany JavaScript')
                urls.extend(links)
            except Exception as exc:
                errors.append(str(exc))
        new_urls = [u for u in dict.fromkeys(urls) if u not in known]
        for url in new_urls[:args.max_details]:
            try:
                data = list(postings(fetcher.get(url)))
                if len(data) != 1:
                    raise RuntimeError('Oczekiwano jednej oferty JobPosting JSON-LD')
                job = parse_offer(data[0],url,source['name'])
                parsed += 1
                match = evaluate(job,profile)
                if match:
                    rows.append(make_row(job,match))
                    known.add(url)
            except Exception as exc:
                errors.append(f'{url}: {exc}')
        if errors:
            failures += 1
        status = 'ERROR' if errors and not parsed else 'PARTIAL' if errors else 'OK'
        message = f'linki={len(set(urls))}; szczegóły={parsed}; poza limitem={max(0,len(new_urls)-args.max_details)}; ' + '; '.join(errors)
        LOG.info('%s %s %s',source['name'],status,message)
        history.append([datetime.now(timezone.utc).isoformat(),source['name'],status,message])
    rows.sort(key=lambda r:int(r[9].rstrip('%')),reverse=True)
    output = Path(args.output)
    output.mkdir(parents=True,exist_ok=True)
    with (output / 'offers.csv').open('w',encoding='utf-8-sig',newline='') as f:
        csv.writer(f).writerows([HEADERS] + rows)
    (output / 'run.json').write_text(json.dumps({'new_matches':len(rows),'history':history},ensure_ascii=False,indent=2),encoding='utf-8')
    if sheet and args.write_sheets:
        sheet.append('Oferty',rows)
        sheet.append('Historia uruchomień',history)
    return 1 if failures else 0


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile',default='profile.json')
    parser.add_argument('--profile-source',choices=['auto','local','sheets'],default='auto')
    parser.add_argument('--init-profile-only',action='store_true')
    parser.add_argument('--sources',default='sources.json')
    parser.add_argument('--output',default='output')
    parser.add_argument('--max-details',type=int,default=100)
    parser.add_argument('--write-sheets',action='store_true')
    raise SystemExit(run(parser.parse_args()))
