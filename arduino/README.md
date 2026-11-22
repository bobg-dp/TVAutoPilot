# TVAutoPilot (Arduino)

Poprzedni firmware na Arduino / PlatformIO. Aktualny program płytki jest w MicroPythonie, w katalogu nadrzędnym. Ten katalog zostaje, bo da się go wgrać z powrotem, gdy telewizor nie sparuje się z wersją w Pythonie.

Mała płytka ESP32, która łączy się z telewizorem jako klawiatura Bluetooth i co 20 minut wysyła jeden klawisz. Dzięki temu Netflix nie zatrzymuje serialu na planszy „Czy nadal oglądasz?” / „Are you still watching?” tylko dlatego, że nikt nie ruszył pilota.

Urządzenie nie loguje się na konto, nie łączy się z Wi-Fi i nie ma aplikacji. Telewizor widzi wyłącznie klawiaturę o nazwie **TVAutoPilot**. Płytka ma być cały czas podłączona do zasilania USB. Nie usypia: sen zerwałby Bluetooth i telewizor przestałby ją widzieć.

## Co wysyła

Po włączeniu startuje **tryb potwierdzenia**. Gdy telewizor jest połączony, pierwszy klawisz idzie dopiero po 20 minutach, kolejne co 20 minut. To Enter, czyli na pilocie OK / wybór. Ta plansza Netflixa zamyka się właśnie tym klawiszem.

**Tryb cichy** wysyła zamiast tego jeden klawisz **F13**. Netflix nie przypisuje F13 do przewijania, pauzy, głośności ani do przesuwania zaznaczenia. Lewo i prawo przewijają film, więc tych klawiszy tu nie ma. Głośność też nie.

F13 jest prawdziwym klawiszem klawiatury (kod HID `0x68`). Biblioteka klawiatury w oryginale kończy mapę na kodzie `0x65`, a wtedy część telewizorów wyrzuca F13 jako nielegalny kod i w ogóle go nie widzi. W katalogu `lib/ESP32-BLE-Keyboard` jest lokalna kopia [T-vK/ESP32-BLE-Keyboard](https://github.com/T-vK/ESP32-BLE-Keyboard) 0.3.2 z trzema zmianami: mapa sięga do F24, parowanie jest bez kodu PIN (telewizor nie ma jak go wpisać), a brakujący deskryptor nie resetuje płytki.

### Ryzyko, którego nie da się usunąć w programie

- Na części Samsungów i LG **Enter w trakcie odtwarzania pauzuje Netflix** albo otwiera pasek. Zanim zostawisz tryb potwierdzenia bez opieki, sprawdź go długim naciśnięciem BOOT w trakcie odcinka.
- Na części telewizorów Netflix zeruje swój licznik tylko wtedy, gdy aplikacja sama obsłuży klawisz. Zignorowane F13 może **nie** powstrzymać planszy. F13 też jej nie zamknie, gdy już wisi na ekranie. Do zamknięcia służy Enter.
- Enter na ekranie głównym telewizora potwierdzi to, co jest akurat podświetlone. Zostaw włączony odcinek, nie menu.
- Starsze telewizory przyjmują tylko klawiaturę Bluetooth Classic. ESP32 w tym projekcie mówi wyłącznie Bluetooth Low Energy. Taki telewizor nie pokaże TVAutoPilot na liście.

Inny „cichy” klawisz (F14, F15, Scroll Lock) ustawia się w `include/config.h`. Scroll Lock bywa pokazywany przez Android TV jako krótki komunikat, dlatego domyślnie jest F13.

## Dioda i przycisk BOOT

Przycisk to **BOOT** (na płytce bywa opisany IO0), nie EN. EN tylko resetuje płytkę. Krótkie naciśnięcie BOOT zmienia tryb do następnego restartu. Przytrzymanie około 3 sekund wysyła aktualny klawisz od razu — do parowania i do sprawdzenia, czy Enter nie pauzuje filmu. Tryb po zaniku prądu wraca do wartości z `include/config.h` (domyślnie potwierdzenie).

| Stan | Tryb potwierdzenia (Enter) | Tryb cichy (F13) |
| --- | --- | --- |
| Szuka telewizora | Wolne pojedyncze mrugnięcie | Wolne podwójne mrugnięcie |
| Połączony | Świeci ciągle | Świeci ciągle, co 3 s dwa krótkie przygaśnięcia |
| Wysłano klawisz | Krótkie mignięcie | Krótkie mignięcie |

Port szeregowy 115200 pokazuje to samo tekstem (`pio device monitor`). Nie trzeba z niego korzystać.

## Jaką płytkę kupić

ESP32 DevKit V1 z modułem **ESP32-WROOM-32**, najlepiej w wersji 30 pinów. Ma mieć gniazdo USB, przycisk BOOT i przycisk EN. Taki układ jest w PlatformIO płytką `esp32dev`.

Nie nadają się:

- ESP8266 — nie ma Bluetooth
- ESP32-S2 — nie ma Bluetooth
- ESP32-S3, C3, C6 — inny układ, ten projekt jest skompilowany pod klasyczny ESP32

Do wgrania programu kabel USB musi przenosić dane, nie tylko ładowanie. Potem wystarczy ładowarka 5 V. Czarny chip przy gnieździe USB to zwykle CH340 albo CP210x. Jeśli komputer nie widzi portu, trzeba sterownika do tego chipu.

Dioda na większości DevKit V1 siedzi na GPIO2 i zapala się stanem wysokim. Gdy mruganie wygląda na odwrócone, w `include/config.h` ustaw `LED_ACTIVE_HIGH` na `0`.

## Wgranie programu

Na komputerze: [Visual Studio Code](https://code.visualstudio.com/) i wtyczka PlatformIO, albo sam PlatformIO Core. Polecenia poniżej uruchamiaj w tym katalogu (`arduino/`). Powrót z MicroPythona wymaga najpierw `esptool erase-flash`, bo układ partycji jest inny. Potem:

```bash
pio run -t upload
```

Samą kompilację, bez płytki, robi `pio run`. Platforma jest przypięta do `espressif32@6.8.1` (Arduino-ESP32 2.0.17), bo na nowszym rdzeniu 3.x tej biblioteki nie da się zbudować.

Gdy wgrywanie nie startuje, przytrzymaj BOOT, naciśnij i puść EN, potem puść BOOT i uruchom polecenie jeszcze raz. Gdy przy 460800 pojawia się timeout, w `platformio.ini` ustaw `upload_speed = 115200`.

Po zmianie czegokolwiek w `include/config.h` program trzeba wgrać ponownie. Sam restart płytki nie czyta pliku z komputera.

## Parowanie

Płytka ogłasza się sama, dopóki dioda mruga. Na liście urządzeń szukaj **TVAutoPilot**. Nie prosi o PIN. Jeden telewizor naraz. Żeby przenieść płytkę na inny odbiornik, na starym usuń TVAutoPilot. Jeśli i tak wraca do starego telewizora, wyczyść pamięć parowania i wgraj od nowa:

```bash
pio run -t erase
pio run -t upload
```

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

## Zmiana odstępu i klawisza

Plik `include/config.h`:

```cpp
#define KEEPALIVE_INTERVAL_MINUTES 20   // co ile minut wysyłać klawisz
#define STARTUP_DELAY_MINUTES 20        // pierwsze wysłanie tyle minut po połączeniu
#define IMMEDIATE_TEST 0                // 1 = próba kilka sekund po połączeniu
#define CONFIRM_MODE_KEY KEY_RETURN     // tryb potwierdzenia, domyślnie Enter
#define SAFE_MODE_KEY KEY_F13           // tryb cichy
#define BOOT_INTO_SAFE_MODE 0           // 1 = po restarcie od razu tryb cichy
```

`IMMEDIATE_TEST` ustaw na `1` tylko na czas próby przy biurku. Na co dzień zostaw `0` i do testu używaj długiego BOOT. `STARTUP_DELAY_MINUTES` przy `IMMEDIATE_TEST 1` jest pomijany.

Klawisze, których program nie przyjmie w żadnym z tych dwóch pól, bo na Netflixie przewijają albo ruszają zaznaczenie: `KEY_LEFT_ARROW`, `KEY_RIGHT_ARROW`, `KEY_UP_ARROW`, `KEY_DOWN_ARROW`. Klawisze głośności i play/pause są innego typu i też się nie skompilują w tym miejscu. To celowe.

Gdy Enter pauzuje film, a F13 nie zatrzymuje planszy, zostaw tryb potwierdzenia na czas oglądania i pogódź się z pauzą albo spróbuj w trybie cichym `KEY_F14` albo `KEY_SCROLL_LOCK`. Każdą zmianę sprawdź długim naciśnięciem w trakcie odcinka, zanim zostawisz płytkę samą.
