# IT scrapper

Python 3.12, publiczny HTML, GitHub Actions i Google Sheets. Bez API portali ofertowych i bez logowania do nich.

## Profil

W trybie zapisu do Sheets profil jest odczytywany z karty **Profil**, przy każdym uruchomieniu. `profile.json` to kopia startowa do pracy offline. Doświadczenie od 2016, Xamarin.Forms, Xamarin.Android, Android Java, POS/PAX, drukarki i płatności kartą. Rzeszów stacjonarnie/hybrydowo lub zdalnie. UoP/B2B, próg 10 000 PLN/mies. Założenie do potwierdzenia: UoP brutto, B2B netto na fakturze. Parser zachowuje oryginalną jednostkę i formę z ogłoszenia; nie wylicza wynagrodzenia na rękę.

Widełki przechodzą filtr, gdy ich górny koniec osiąga próg. Stawka godzinowa: orientacyjnie 160 h/mies. Brak widełek, obca waluta lub nieznana jednostka oznaczają weryfikację, a nie odrzucenie. To punktacja słów kluczowych, nie analiza CV przez AI ani prawdopodobieństwo zatrudnienia. Kotlin, MAUI, C#, Wear OS i Compose są niepotwierdzone. Staż nie jest automatycznym dowodem seniority.

## Uruchomienie lokalne

```sh
python -m venv .venv
# Aktywuj środowisko .venv zgodnie z systemem
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scraper.py --max-details 100
```

Domyślnie tylko `output/offers.csv` i `output/run.json`, bez zapisu do Google. CSV zawiera dane zewnętrzne; do importowania do arkusza zalecany jest zapis przez API w trybie RAW, bez wykonywania formuł.

## Źródła i granice wersji 0.1

- Just Join IT: listy Mobile oraz .NET, linki z HTML, szczegóły z osadzonego JSON-LD JobPosting. Sprawdzone na żywo 27.10.2026.
- No Fluff Jobs i Pracuj.pl: pobieranie HTML i JobPosting sprawdzone na żywo 27.10.2026, po 12 szczegółów na źródło. Wcześniejsze pojedyncze żądania zwracały HTTP 403; dostęp może się różnić na runnerach GitHub. Bez obchodzenia blokad.
- LinkedIn: wyłączony, niezaimplementowany.
- Każde źródło sprawdza robots.txt; błąd pobrania zasad zatrzymuje to źródło. Bez obchodzenia CAPTCHA, 403 i logowania.
- Obecnie zbierana jest pierwsza strona HTML każdej skonfigurowanej listy. Brak przewijania JS i pełnej paginacji: nie jest to komplet wszystkich ofert rynku. Limit szczegółów dotyczy każdego źródła; liczba pominiętych linków trafia do raportu.
- Dedup po kanonicznym URL i linkach już obecnych w zakładce Oferty. Brak deduplikacji między portalami. Odrzucone oferty mogą być ponownie oceniane przy kolejnym uruchomieniu.
- Oferty raz zapisane nie są automatycznie odświeżane ani oznaczane jako wygasłe. Nowe wygasłe ogłoszenia są odrzucane, jeżeli publikują datę ważności.
- Wynik zależy od deklaracji lokalizacji i zdalności w JSON-LD. Szczegóły modelu hybrydowego oraz ograniczenia kraju wymagają sprawdzenia w ogłoszeniu.

## Google Cloud / Sheets — konfiguracja do wykonania

Projekt: `it-job-scraper-512908`.
Arkusz: `1sCvXrQan3ahjrFEUb6pLK6y4L3_oQ6_6qnzWO4QILKE`.

1. Włącz Google Sheets API oraz usługi wymagane przez Workload Identity Federation.
2. Utwórz konto usługi, np. `job-scraper`. Nie potrzebuje roli Editor całego projektu do edycji udostępnionego arkusza.
3. Udostępnij wskazany arkusz adresowi konta usługi jako Edytor.
4. Skonfiguruj Workload Identity Pool i dostawcę OIDC z issuer `https://token.actions.githubusercontent.com`.
5. Ogranicz zaufanie do repo `dvp4011-sys/it-scrapper`, właściciela i właściwej gałęzi. Preferuj niezmienne identyfikatory numeryczne repo/właściciela w warunku dostawcy. Przyznaj tożsamości workflow rolę `roles/iam.workloadIdentityUser` na tym koncie usługi.
6. W GitHub → Settings → Secrets and variables → Actions → Variables dodaj:

| Zmienna | Wartość |
|---|---|
| GOOGLE_SHEET_ID | 1sCvXrQan3ahjrFEUb6pLK6y4L3_oQ6_6qnzWO4QILKE |
| GCP_SERVICE_ACCOUNT_EMAIL | adres utworzonego konta usługi |
| GCP_WORKLOAD_IDENTITY_PROVIDER | projects/NUMER/locations/global/workloadIdentityPools/POOL/providers/PROVIDER |
| SCRAPER_ENABLED | true dopiero po poprawnym teście zapisu |

Przy OIDC nie potrzeba stałego sekretu JSON. Nie zapisuj poświadczeń w repo. Dokumentacja: https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines

## GitHub Actions

Workflow `Scrape IT jobs`: ręcznie z opcją zapisu do Sheets albo co 2 dni o 06:17 UTC (07:17 zimą / 08:17 latem w Polsce), licząc od 27.10.2026. Codzienny trigger sprawdza parzystość liczby dni; w dni pomiędzy pobieranie jest pomijane. Dzięki temu odstęp pozostaje równy 2 dni także na granicach miesięcy. Harmonogram działa z domyślnej gałęzi i może się opóźniać. Dopóki `SCRAPER_ENABLED` nie jest `true`, harmonogram pomija zadanie. Ręczne uruchomienie domyślnie generuje tylko artefakt CSV/JSON.

Workflow nie nadpisuje ręcznych statusów, rozmów, terminów ani notatek: dopisuje wyłącznie nowe wiersze. Tworzy dedykowane zakładki `Oferty` i `Historia uruchomień`; przy niezgodnym nagłówku zatrzymuje zapis. Inne zakładki pozostają bez zmian. Nagłówki odpowiadają dostarczonemu wzorowi, z dodatkowymi kolumnami wyjaśnienia i lokalizacji. Formatowanie wizualne arkusza pozostaje kolejnym etapem.

Błąd choćby jednego źródła powoduje czerwony status workflow po zapisaniu częściowych wyników. Szczegóły są w logach i artefakcie run.json; nie oznacza to braku ofert z pozostałych źródeł. Dla pilotażu wyłącz niedostępne źródła w sources.json, jeżeli mają być pomijane.

## Weryfikacja pierwszej wersji

10 testów jednostkowych zakończonych powodzeniem. Próba sieciowa: po 12 szczegółów z Just Join IT, No Fluff Jobs i Pracuj.pl, wszystkie źródła bez błędów, 10 dopasowań łącznie. To ograniczona próba, nie dowód pełnego pokrycia. Zapis do Google Sheets i OIDC nie były jeszcze testowane z kontem użytkownika.

## Następne etapy

Pełna paginacja i kontrola pokrycia, trwała pamięć odrzuconych ofert, odświeżanie ogłoszeń, duplikaty między portalami, profil z CV, precyzyjne wymagania i luki, formatowanie arkusza. Sugestie do CV wyłącznie po potwierdzeniu doświadczenia — kolumna jest obecnie celowo pusta.


## Edycja profilu w arkuszu

Karta **Profil** jest źródłem konfiguracji dla harmonogramu i ręcznych uruchomień z `write_sheets=true`. Przy pierwszym uruchomieniu jest zakładana i wypełniana danymi startowymi; istniejąca karta nigdy nie jest resetowana. Zmiany obowiązują od następnego uruchomienia. Bez zapisu do Sheets domyślnie używany jest lokalny `profile.json`; do próby z profilem arkusza bez zapisu ofert: `python scraper.py --profile-source sheets`.

Kolumny: Typ, Nazwa, Hasła / aliasy (|), Wartość, Waga, Poziom 0–5, Lata doświadczenia, Aktywne, Zakres, Uwagi.

- `ustawienie`: miasto (kilka miast rozdziel `|`), zdalność TAK/NIE, minimum PLN, godziny miesięcznie, próg Match, rok rozpoczęcia doświadczenia i zachowanie ofert bez widełek.
- `rola`: kwalifikuje ofertę po hasłach w tytule lub całości, według kolumny Zakres. Nie dodaje punktów.
- `skill` lub `własne`: własne hasła, skille, domeny i integracje sprzętowe. Oba typy są oceniane tak samo. Dopisuj nowe wiersze także poniżej przykładów; odczytywane jest całe A:J.
- Waga 0–100 określa znaczenie trafienia. Poziom: 0 brak znajomości, 1 podstawy, 2 praktyczny, 3 dobry, 4 zaawansowany, 5 ekspert. Punkty = waga × poziom / 5. Pusty poziom oznacza potwierdzone doświadczenie bez oceny poziomu (75% wagi). `?` oznacza niepotwierdzony skill (zero punktów i wpis w Lukach, jeśli wystąpi w ofercie).
- Lata przy skillu są opcjonalnym opisem stażu kandydata i pojawiają się w uzasadnieniu trafienia. Nie są automatycznie porównywane z wymaganiem konkretnej technologii w ogłoszeniu; parser nie potrafi tego wiarygodnie ustalić. Rok 2016 dotyczy łącznego doświadczenia. Nie przypisujemy tego stażu wszystkim skillom. Jawne wymagania większego stażu ogólnego są oznaczane do sprawdzenia.
- Match to suma punktów ograniczona do 95, nadal prezentowana w istniejącej kolumnie procentowej dla zgodności układu. Nie jest znormalizowanym procentem spełnionych wymagań ani szansą zatrudnienia. Alias lub skill może wystąpić w wymaganiu opcjonalnym albo negacji; ocena wymaga przeczytania oferty.
- Nowy startowy próg Match to 15 punktów, zamiast dawnych 25: nieocenione poziomy mają teraz mnożnik 75%. Potwierdzone skille mają puste poziomy i lata; skille niewskazane przez kandydata mają `?`. Przykłady CI/CD, SOLID, Clean Architecture, REST i Agile są wyłączone do samodzielnego uzupełnienia.
- Hasła są literalne, rozdzielane `|`; bez wykonywania regexu lub kodu z arkusza. Java nie trafia w JavaScript, POS nie trafia w position. Odmiany językowe trzeba wpisać jako aliasy.
- Zmiana profilu nie przelicza starych ofert, nie zmienia ręcznych statusów i nie rozszerza list stron źródłowych: aktualnie listy mobile/.NET oraz Android/Xamarin. Zmiana roli na inny obszar IT wymaga też rozszerzenia `sources.json`.
- Błędny nagłówek, duplikat aktywnej nazwy, niepoprawna liczba lub brak obowiązkowego ustawienia zatrzymuje uruchomienie z numerem wiersza. Brak dostępu do karty nie uruchamia cichego powrotu do starego profilu JSON.

Opcja ręcznego workflow `init_profile_only=true` tworzy lub waliduje kartę Profil bez pobierania ofert. Ustawienia wymagające zmiany OIDC lub uprawnień Google nie są częścią profilu.
