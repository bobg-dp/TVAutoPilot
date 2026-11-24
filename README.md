# TVAutoPilot

Mała płytka ESP32, która łączy się z telewizorem jako klawiatura Bluetooth i co 20 minut wysyła OK. Dzięki temu Netflix nie zatrzymuje serialu na planszy „Czy nadal oglądasz?” / „Are you still watching?” tylko dlatego, że nikt nie ruszył pilota.

Program jest w MicroPythonie. Telewizor widzi wyłącznie klawiaturę o nazwie **TVAutoPilot**. Płytka nie loguje się na konto i nie łączy się z Wi-Fi. Ma być cały czas podłączona do zasilania USB. Nie usypia: sen zerwałby Bluetooth i telewizor przestałby ją widzieć.

Poprzedni firmware na Arduino jest w katalogu `arduino/`. Zostaje, bo część telewizorów jest wybredna przy parowaniu, a tamta wersja jest już sprawdzona na tej płytce.

## Co wysyła

Po włączeniu startuje **tryb potwierdzenia**. Gdy telewizor się połączy, po 60 sekundach idą **dwa OK** z przerwą 2 sekund, i tak samo co 20 minut. To Enter, czyli na pilocie OK / wybór. Pierwsze z pary może spauzować film, drugie wraca do odtwarzania. Pojedyncze OK nie jest wysyłane: płytka nie widzi, czy telewizor gra, stoi na pauzie, czy pokazuje planszę, więc nie da się dobrać jednego naciśnięcia do stanu ekranu. Ta plansza Netflixa zamyka się właśnie tym klawiszem.

**Tryb cichy** wysyła zamiast tego jeden klawisz **F13**. Netflix nie przypisuje F13 do przewijania, pauzy, głośności ani do przesuwania zaznaczenia. Lewo i prawo przewijają film, więc tych klawiszy tu nie ma. Głośność też.

F13 jest prawdziwym klawiszem klawiatury (kod HID `0x68`). Mapa raportu w `ble_keyboard.py` sięga do F24 (kod `0x73`). Mapa urwana na `0x65` sprawia, że część telewizorów wyrzuca F13 jako nielegalny kod i w ogóle go nie widzi. Parowanie jest bez kodu PIN: telewizor nie ma jak go wpisać. Klucze sparowania zostają w pliku `bonds.txt` na płytce i przeżywają restart. Kasuje je wyczyszczenie pamięci flash albo usunięcie tego pliku.

### Ryzyko, którego nie da się usunąć w programie

- Na części Samsungów i LG **Enter w trakcie odtwarzania pauzuje Netflix** albo otwiera pasek. Drugie OK ma puścić film dalej. Zanim zostawisz tryb potwierdzenia bez opieki, sprawdź go długim naciśnięciem BOOT w trakcie odcinka.
- Na części telewizorów Netflix zeruje swój licznik tylko wtedy, gdy aplikacja sama obsłuży klawisz. Zignorowane F13 może **nie** powstrzymać planszy. F13 też jej nie zamknie, gdy już wisi na ekranie. Do zamknięcia służy Enter.
- Enter na ekranie głównym telewizora potwierdzi to, co jest akurat podświetlone. Zostaw włączony odcinek, nie menu.
- Starsze telewizory przyjmują tylko klawiaturę Bluetooth Classic. ESP32 w tym projekcie mówi wyłącznie Bluetooth Low Energy. Taki telewizor nie pokaże TVAutoPilot na liście.
- Po zmianie z firmware Arduino na MicroPythona telewizor pamięta stare klucze przy tym samym adresie Bluetooth. Trzeba usunąć TVAutoPilot z listy urządzeń w telewizorze i sparować jeszcze raz.

Inny „cichy” klawisz (F14, F15, Scroll Lock) ustawia się w `config.py`. Scroll Lock bywa pokazywany przez Android TV jako krótki komunikat, dlatego domyślnie jest F13.

## Dioda i przycisk BOOT

Przycisk to **BOOT** (na płytce bywa opisany IO0), nie EN. EN tylko resetuje płytkę. Krótkie naciśnięcie BOOT zmienia tryb do następnego restartu. Przytrzymanie około 3 sekund w trybie potwierdzenia wysyła od razu dwa OK — do parowania i do sprawdzenia, czy film wraca po pauzie. W trybie cichym wysyła jeden klawisz F13. Tryb po zaniku prądu wraca do wartości z `config.py` (domyślnie potwierdzenie).

| Stan | Tryb potwierdzenia (Enter) | Tryb cichy (F13) |
| --- | --- | --- |
| Szuka telewizora | Wolne pojedyncze mrugnięcie | Wolne podwójne mrugnięcie |
| Połączony | Świeci ciągle | Świeci ciągle, co 3 s dwa krótkie przygaśnięcia |
| Wysłano klawisz | Krótkie mignięcie | Krótkie mignięcie |

Port szeregowy 115200 pokazuje to samo tekstem. Nie trzeba z niego korzystać.

## Jaką płytkę kupić

ESP32 DevKit V1 z modułem **ESP32-WROOM-32**, najlepiej w wersji 30 pinów. Ma mieć gniazdo USB, przycisk BOOT i przycisk EN. Do wgrania programu kabel USB musi przenosić dane, nie tylko ładowanie. Potem wystarczy ładowarka 5 V. Czarny chip przy gnieździe USB to zwykle CH340 albo CP210x. Jeśli komputer nie widzi portu, trzeba sterownika do tego chipu.

Nie nadają się ESP8266 ani ESP32-S2 (nie mają Bluetooth). ESP32-S3, C3 i C6 wymagają innego pliku firmware MicroPythona niż ten opisany poniżej.

Dioda na większości DevKit V1 siedzi na GPIO2 i zapala się stanem wysokim. Gdy mruganie wygląda na odwrócone, w `config.py` ustaw `LED_ACTIVE_HIGH = False`.

## Wgranie programu

Na komputerze: Python 3 i dwa pakiety.

```bash
python3 -m pip install esptool mpremote
```

Firmware MicroPythona: stabilne wydanie **ESP32 / WROOM**, wariant generic (nie SPIRAM, nie D2WD, nie Unicore). Na stronie [micropython.org/download/ESP32_GENERIC](https://micropython.org/download/ESP32_GENERIC/) link nazywa się tylko „.bin” przy v1.29.0 (2026-08-24). Plik ściąga się tak:

```bash
curl -L -o ESP32_GENERIC-20260824-v1.29.0.bin https://micropython.org/resources/firmware/ESP32_GENERIC-20260824-v1.29.0.bin
```

Pierwsze wgranie kasuje dotychczasowy program Arduino. Port na macOS wygląda jak `/dev/cu.usbserial-…`, `/dev/cu.wchusbserial…` albo `/dev/cu.SLAB_USBtoUART`. Podstaw swoją nazwę zamiast `PORT`.

```bash
esptool --port PORT erase-flash
esptool --port PORT --baud 460800 write-flash 0x1000 ESP32_GENERIC-20260824-v1.29.0.bin
mpremote connect PORT cp config.py ble_keyboard.py main.py :
mpremote connect PORT reset
```

Gdy wgrywanie staje przy 460800, powtórz `write-flash` bez `--baud 460800`. Gdy płytka nie wchodzi w tryb wgrywania, przytrzymaj BOOT, naciśnij i puść EN, potem puść BOOT i uruchom polecenie jeszcze raz.

Podgląd tekstu: `mpremote connect PORT`. Wyjście z podglądu: Ctrl-X.

Po zmianie `config.py` nie wgrywa się całego firmware. Wystarczy:

```bash
mpremote connect PORT cp config.py :
mpremote connect PORT reset
```

To samo dotyczy `main.py` i `ble_keyboard.py`.

Żeby telewizor zapomniał płytkę, usuń TVAutoPilot z jego listy, a na płytce skasuj klucze. W podglądzie `mpremote`:

```python
import os
os.remove("bonds.txt")
```

Potem zresetuj płytkę (przycisk EN albo `mpremote connect PORT reset`) i sparuj od nowa. `esptool erase-flash` kasuje i klucze, i MicroPythona: firmware oraz trzy pliki `.py` trzeba wgrać ponownie.

## Parowanie

Płytka ogłasza się sama, dopóki dioda mruga. Na liście urządzeń szukaj **TVAutoPilot**. Nie prosi o PIN. Jeden telewizor naraz. Żeby przenieść płytkę na inny odbiornik, na starym usuń TVAutoPilot i skasuj `bonds.txt`, jak wyżej.

Nazwy menu zależą od rocznika. Chodzi o dodanie klawiatury Bluetooth.

**Samsung (Tizen)**  
Ustawienia → Ogólne → Menedżer urządzeń zewnętrznych → Menedżer urządzeń wejściowych → Lista urządzeń Bluetooth.  
Na części modeli: Ustawienia → Połączenia → Bluetooth.

**LG (webOS)**  
Ustawienia → Wszystkie ustawienia → Ogólne → Urządzenia → Klawiatura Bluetooth (albo Urządzenia Bluetooth).

**Android TV / Google TV**  
Ustawienia → Pilot i akcesoria → Dodaj urządzenie.  
Na Google TV: Ustawienia → Piloty i akcesoria → Sparuj zdalny lub akcesorium.

Po sparowaniu dioda świeci ciągle (w trybie cichym co kilka sekund na moment przygasa). Telewizor zapamiętuje płytkę i łączy się sam po włączeniu, o ile TVAutoPilot jest w zasięgu i ma zasilanie. Postaw płytkę obok telewizora, nie za metalową osłoną.

Gdy telewizor w ogóle nie pokazuje płytki albo łączy się i zaraz zrywa, wgraj z powrotem firmware z katalogu `arduino/` (po `esptool erase-flash`).

## Zmiana odstępu i klawisza

Plik `config.py`. Wartości klawiszy to kody HID, nie stare numery z Arduino (`KEY_RETURN` to `0x28`, `KEY_F13` to `0x68`).

```python
KEEPALIVE_INTERVAL_MINUTES = 20   # co ile minut wysyłać dwa OK
FIRST_OK_DELAY_SECONDS = 60       # dwa OK tyle sekund po połączeniu
DOUBLE_OK_GAP_SECONDS = 2         # przerwa między dwoma OK
IMMEDIATE_TEST = False            # True = pojedyncze OK co kilka sekund, bez pary
CONFIRM_MODE_KEY = KEY_RETURN     # albo KEY_DOWN_ARROW (strzałka w dół)
SAFE_MODE_KEY = KEY_F13           # tryb cichy
BOOT_INTO_SAFE_MODE = False       # True = po restarcie od razu tryb cichy
```

`IMMEDIATE_TEST` ustaw na `True` tylko na czas próby przy biurku. Wtedy zostają pojedyncze OK: pierwszy po `IMMEDIATE_TEST_DELAY_SECONDS` (domyślnie 5 s), kolejne co `IMMEDIATE_TEST_INTERVAL_SECONDS` (domyślnie 30 s). Na co dzień zostaw `False`. `FIRST_OK_DELAY_SECONDS` przy `IMMEDIATE_TEST = True` jest pomijany.

W trybie potwierdzenia zamiast Entera można ustawić `KEY_DOWN_ARROW`. Dwa naciśnięcia schodzą wtedy w dół po zaznaczeniu, a nie wysyłają OK. `KEY_LEFT_ARROW`, `KEY_RIGHT_ARROW` i `KEY_UP_ARROW` program odrzuci: lewo i prawo przewijają film, góra rusza zaznaczenie w drugą stronę. W trybie cichym strzałka w dół też jest odrzucona. Klawisze głośności i play/pause są poza mapą raportu i też zostaną odrzucone przy starcie. To celowe.

Gdy para OK zostawia film zapauzowany, spróbuj w trybie cichym `KEY_F14` albo `KEY_SCROLL_LOCK`. Każdą zmianę sprawdź długim naciśnięciem w trakcie odcinka, zanim zostawisz płytkę samą.
