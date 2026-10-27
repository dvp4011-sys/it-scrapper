"""Editable candidate configuration stored as ordinary rows in Google Sheets."""
import math
import re
import unicodedata
from datetime import date

PROFILE_HEADERS = ['Typ', 'Nazwa', 'Hasła / aliasy (|)', 'Wartość', 'Waga', 'Poziom 0–5', 'Lata doświadczenia', 'Aktywne', 'Zakres', 'Uwagi']
SETTINGS = {
 'Miasto': ('city', 'text'), 'Praca zdalna': ('remote', 'bool'),
 'Minimum miesięcznie PLN': ('minimum_monthly_pln', 'number'),
 'Godziny miesięcznie': ('hourly_month_hours', 'number'),
 'Minimalny Match': ('minimum_score', 'number'),
 'Doświadczenie od roku': ('experience_since', 'number'),
 'Oferty bez widełek': ('keep_unknown_salary', 'bool'),
}


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value).lower()) if not unicodedata.combining(c)).replace('ł', 'l')


def boolean(value):
    v = normalize(value).strip()
    if v in ['tak', 'true', '1']: return True
    if v in ['nie', 'false', '0']: return False
    raise ValueError('Oczekiwano TAK lub NIE')


def number(value, low, high):
    n = float(str(value).replace(',', '.'))
    if not math.isfinite(n) or not low <= n <= high:
        raise ValueError(f'Liczba musi być w przedziale {low}–{high}')
    return n


def aliases_match(aliases, content):
    content = normalize(content)
    return any(re.search(r'(?<!\w)' + re.escape(normalize(a)) + r'(?!\w)', content) for a in aliases)


def default_rows():
    rows = [PROFILE_HEADERS]
    def setting(name, value, note=''):
        rows.append(['ustawienie', name, '', value, '', '', '', 'TAK', '', note])
    setting('Miasto', 'Rzeszów', 'Stacjonarnie lub hybrydowo w tym mieście; można podać kilka miast rozdzielonych |.')
    setting('Praca zdalna', 'TAK', 'Zdalność według ogłoszenia; sprawdź ograniczenia kraju i wizyty w biurze.')
    setting('Minimum miesięcznie PLN', 10000, 'UoP brutto / B2B netto na fakturze — założenie do potwierdzenia. Wystarczy górny koniec widełek.')
    setting('Godziny miesięcznie', 160, 'Przeliczenie stawek godzinowych.')
    setting('Minimalny Match', 15, 'Próg punktów 0–95; to heurystyka, nie szansa zatrudnienia.')
    setting('Doświadczenie od roku', 2016, 'Łączny staż; nie oznacza tylu lat w każdej technologii.')
    setting('Oferty bez widełek', 'TAK', 'Obce waluty i nieznana jednostka też wymagają weryfikacji.')
    roles = [('Android Developer','android'),('Xamarin Developer','xamarin'),('Mobile Developer','mobile|mobilny|mobilnych'),('MAUI Developer','maui'),('POS / płatności','pos|pax|payment|payments|płatności')]
    for name, aliases in roles:
        rows.append(['rola',name,aliases,'',0,'','','TAK','tytuł','Role służą do kwalifikacji oferty, nie dodają punktów.'])
    skills = [
      ('skill','Xamarin.Forms','xamarin.forms|xamarin forms|xamarin',40,''),
      ('skill','Xamarin.Android','xamarin.android|xamarin android',30,''),
      ('skill','Android','android',25,''),
      ('skill','Java','java',15,''),
      ('własne','PAX','pax',15,''),
      ('własne','POS / terminale','pos|point of sale|terminal|terminale|terminali|terminals',10,''),
      ('własne','Płatności kartą','card payment|card payments|payment|payments|płatności|płatnościami|card acquiring',5,''),
      ('własne','Drukarki','printer|printers|drukarka|drukarki|drukarek',5,''),
      ('własne','Aplikacje na zegarki','smartwatch|smartwatches|wearable|wearables|zegarki',5,''),
      ('skill','Kotlin','kotlin',15,'?'),('skill','.NET MAUI','.net maui|maui',15,'?'),
      ('skill','C#','c#|csharp',10,'?'),('skill','Wear OS','wear os',10,'?'),
      ('skill','Jetpack Compose','jetpack compose',10,'?'),
    ]
    for kind,name,aliases,weight,level in skills:
        rows.append([kind,name,aliases,'',weight,level,'','TAK','całość','Niepotwierdzona znajomość — uzupełnij poziom.' if level == '?' else 'Potwierdzone doświadczenie; uzupełnij poziom i lata.'])
    for name,aliases in [('CI/CD','ci/cd|continuous integration'),('SOLID','solid'),('Clean Architecture','clean architecture'),('REST API','rest|restful'),('Agile / Scrum','agile|scrum')]:
        rows.append(['skill',name,aliases,'',5,'?','','NIE','całość','Przykładowe hasło rekrutacyjne. Włącz i uzupełnij własny poziom, jeśli dotyczy.'])
    rows.append(['instrukcja','Skala poziomów','','','','','','','','Pusty = potwierdzone bez oceny (75% wagi); ? = niepotwierdzone (0 pkt). 0 brak; 1 podstawy; 2 praktyczny; 3 dobry; 4 zaawansowany; 5 ekspert. Punkty = waga × poziom / 5.'])
    rows.append(['instrukcja','Jak dopisywać','','','','','','','','Dopisz wiersz typu skill, własne lub rola. Aliasy rozdziel |; waga 0–100; aktywne TAK/NIE; zakres tytuł lub całość. Nie zmieniaj nagłówków. Wagi wpływają na kolejne oceny; istniejące oferty nie są przeliczane.'])
    return rows


def parse_profile(rows):
    if not rows or rows[0] != PROFILE_HEADERS:
        raise ValueError('Profil: niezgodne nagłówki A1:J1')
    result, rules, roles, seen = {}, [], [], set()
    for index, raw in enumerate(rows[1:], 2):
        cells = list(raw) + [''] * (10 - len(raw))
        kind, name, aliases, value, weight, level, years, active, scope, note = [str(x).strip() for x in cells[:10]]
        if not any(cells) or kind == 'instrukcja': continue
        try:
            if not boolean(active): continue
            if not name: raise ValueError('Brak nazwy')
            key = (kind, normalize(name))
            if key in seen: raise ValueError('Powtórzona nazwa')
            seen.add(key)
            if kind == 'ustawienie':
                if name not in SETTINGS: raise ValueError('Nieznane ustawienie: '+name)
                key, typ = SETTINGS[name]
                result[key] = boolean(value) if typ == 'bool' else number(value, 0, 10000000) if typ == 'number' else value
            elif kind in ['skill','własne','rola']:
                terms = [a.strip() for a in aliases.split('|') if a.strip()]
                if not terms: raise ValueError('Brak haseł / aliasów')
                if scope not in ['tytuł','całość']: raise ValueError('Zakres: tytuł lub całość')
                rule = dict(name=name, aliases=terms, scope=scope, weight=number(weight or 0,0,100), level=None if level == '?' else number(level,0,5) if level else 'confirmed', years=number(years,0,80) if years else None)
                (roles if kind == 'rola' else rules).append(rule)
            else: raise ValueError('Typ: ustawienie, rola, skill, własne lub instrukcja')
        except (ValueError, TypeError) as exc:
            raise ValueError(f'Profil, wiersz {index}: {exc}') from exc
    missing = [key for key, typ in SETTINGS.values() if key not in result]
    if missing: raise ValueError('Profil: brakuje ustawień '+', '.join(missing))
    if not roles or not rules: raise ValueError('Profil: włącz przynajmniej jedną rolę i jeden skill / własny wpis')
    if not result['city']: raise ValueError('Profil: brak miasta')
    if result['hourly_month_hours'] <= 0: raise ValueError('Profil: godziny miesięcznie muszą być dodatnie')
    if not 0 <= result['minimum_score'] <= 95: raise ValueError('Profil: Match musi być w zakresie 0–95')
    if not 1900 <= result['experience_since'] <= date.today().year or not result['experience_since'].is_integer(): raise ValueError('Profil: niepoprawny rok doświadczenia')
    result.update(rules=rules, roles=roles, unconfirmed=[r['name'] for r in rules if r['level'] is None])
    return result


def rank_keywords(title, body, profile):
    def matches(rule):
        return aliases_match(rule['aliases'], title if rule['scope'] == 'tytuł' else title+' '+body)
    if not any(matches(r) for r in profile['roles']): return None
    score, reasons, gaps = 0, [], []
    for rule in profile['rules']:
        if not matches(rule): continue
        level = rule['level']
        if level is None or level == 0:
            gaps.append(rule['name'] + (' — do potwierdzenia' if level is None else ' — brak znajomości'))
            continue
        factor = 0.75 if level == 'confirmed' else level / 5
        points = rule['weight'] * factor
        score += points
        detail = f"{rule['name']}: +{points:g} pkt"
        if rule['years'] is not None: detail += f"; kandydat {rule['years']:g} lat"
        reasons.append(detail)
    # Only explicit experience requirements; no inference of per-skill tenure.
    for required in re.findall(r'(\d+)\+?\s*(?:years? of (?:professional )?experience|lat(?:a)? doświadczenia)', title+' '+body, flags=re.I):
        available = date.today().year - int(profile['experience_since'])
        if int(required) > available:
            gaps.append(f'Wymóg {required} lat doświadczenia; profil od {int(profile["experience_since"])} — zweryfikuj zakres')
    return score, reasons, gaps
