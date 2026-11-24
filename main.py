# TVAutoPilot
#
# An ESP32 that stays paired as a BLE HID keyboard and, on a timer, sends
# a key so Netflix does not stop on "Are you still watching?".
#
# Confirm mode (default): Enter / OK, always as a pair two seconds apart.
# On some TVs the first press pauses playback and the second resumes it.
# The board cannot see whether the set is playing, paused, or showing the
# prompt, so this mode never sends a lone OK. Try it with a long BOOT
# press before it is left running.
#
# Safe mode: the single key in config.py, default F13. Netflix does not
# bind F13 to seek, pause, or volume. It may also fail to count F13 as
# activity. See config.py.
#
# The loop never light-sleeps and never deep-sleeps. Either one drops the
# Bluetooth link, and the TV would have to pair again. The radio stays up
# for as long as the board has USB power.

import time

from machine import Pin

import config
from ble_keyboard import BleKeyboard

_MODE_CONFIRM = "potwierdzenie"
_MODE_SAFE = "cichy"


class App:
    def __init__(self):
        self.keyboard = BleKeyboard(config.DEVICE_NAME)
        self.mode = _MODE_SAFE if config.BOOT_INTO_SAFE_MODE else _MODE_CONFIRM
        self.button = Pin(config.BUTTON_PIN, Pin.IN, Pin.PULL_UP)
        self.led = Pin(config.LED_PIN, Pin.OUT)
        self.was_connected = False
        self.stable_down = False
        self.last_read_down = False
        self.long_press_sent = False
        self.last_bounce_ms = time.ticks_ms()
        self.press_started_ms = 0
        self.next_key_at_ms = time.ticks_ms()
        self.flash_until_ms = 0
        # owe: the first OK of a pair was released, the second was not.
        # held: the press report went out and the key is still down.
        self._owe_second_ok = False
        self._ok_held = False
        self._write_led(False)

    def run(self):
        time.sleep_ms(200)
        self.keyboard.start()
        print("TVAutoPilot")
        print("Tryb po starcie: %s. Odstęp: %s." % (self.mode, self._interval_label()))
        print("Krótkie BOOT: zmiana trybu. Przytrzymanie ok. 3 s: wyślij teraz.")
        print("Szukam telewizora. Na liście Bluetooth: %s." % config.DEVICE_NAME)
        while True:
            self._loop(time.ticks_ms())
            # Yield so the idle task can run. Do not replace this with
            # lightsleep or deepsleep: the BLE connection would drop.
            time.sleep_ms(10)

    def _loop(self, now):
        self._poll_button(now)
        self._service_schedule(now)
        self._apply_led(now)

    def _interval_ms(self):
        if config.IMMEDIATE_TEST:
            return config.IMMEDIATE_TEST_INTERVAL_SECONDS * 1000
        return config.KEEPALIVE_INTERVAL_MINUTES * 60000

    def _interval_label(self):
        if config.IMMEDIATE_TEST:
            return "%d s" % config.IMMEDIATE_TEST_INTERVAL_SECONDS
        return "%d min" % config.KEEPALIVE_INTERVAL_MINUTES

    def _first_key_delay_ms(self):
        if config.IMMEDIATE_TEST:
            return config.IMMEDIATE_TEST_DELAY_SECONDS * 1000
        return config.FIRST_OK_DELAY_SECONDS * 1000

    def _active_key(self):
        if self.mode == _MODE_SAFE:
            return config.SAFE_MODE_KEY
        return config.CONFIRM_MODE_KEY

    def _write_led(self, on):
        lit = on if config.LED_ACTIVE_HIGH else not on
        self.led.value(1 if lit else 0)

    # Advertising: slow blink. Confirm is one flash, safe is two, so the mode
    # is visible before the TV connects.
    # Connected: solid. Safe mode dips the LED twice every 3 s so a solid lamp
    # still tells the modes apart from across the room.
    # A key send inverts the pattern for a short window (the brief flash).
    def _pattern_on(self, now, connected):
        # Test mode is a slow square wave. The daily pattern is a 180 ms
        # blip, which is easy to miss, and a power LED on the board stays
        # lit either way. Active-low and active-high LEDs both blink here.
        if config.IMMEDIATE_TEST:
            if connected:
                return (now % 1000) >= 200
            return (now % 1000) < 500
        if not connected:
            t = now % 2000
            if self.mode == _MODE_CONFIRM:
                return t < 180
            return t < 140 or (280 <= t < 420)
        if self.mode == _MODE_CONFIRM:
            return True
        t = now % 3000
        dip = t < 70 or (160 <= t < 230)
        return not dip

    def _apply_led(self, now):
        on = self._pattern_on(now, self.keyboard.connected)
        if time.ticks_diff(self.flash_until_ms, now) > 0:
            on = not on
        self._write_led(on)

    def _confirm_pair(self):
        return self.mode == _MODE_CONFIRM and not config.IMMEDIATE_TEST

    # 1 = press and release both queued. 0 = press did not go out.
    # -1 = the key is still down, so another press would not be a new OK.
    def _tap_result(self):
        if not self.keyboard.connected:
            print("Nie wysłano: telewizor nie jest połączony.")
            return 0
        result = self.keyboard.tap(self._active_key(), config.KEY_HOLD_MS)
        if result == 0:
            print("Nie wysłano: telewizor odrzucił raport.")
            return 0
        self.flash_until_ms = time.ticks_add(time.ticks_ms(), 160)
        if result < 0 and not self.keyboard.release_all():
            print("Naciśnięcie wyszło, puszczenie klawisza nie.")
            return -1
        return 1

    def _tap_once(self):
        result = self._tap_result()
        if result < 0:
            self._ok_held = True
            return False
        return result == 1

    def _note_sent(self, what):
        self.next_key_at_ms = time.ticks_add(time.ticks_ms(), self._interval_ms())
        print(
            "Wysłano %s 0x%02X (tryb %s). Następny za %s."
            % (what, self._active_key(), self.mode, self._interval_label())
        )

    def _backoff(self):
        self.next_key_at_ms = time.ticks_add(time.ticks_ms(), 5000)

    # Test mode and safe mode stay a single key.
    # Confirm mode always sends two OK presses. The board cannot see
    # whether the TV accepted Enter, so a lone OK is never the plan:
    # one press can pause playback, and the next pair would leave it paused.
    def _send_scheduled(self):
        if self._ok_held:
            if not self.keyboard.release_all():
                self._backoff()
                return
            self._ok_held = False
            if self._confirm_pair():
                if self._owe_second_ok:
                    self._owe_second_ok = False
                    self._note_sent("dwa OK")
                    return
                self._owe_second_ok = True
        if self._confirm_pair():
            if self._owe_second_ok:
                self._send_owed_second()
                return
            self._start_pair()
            return
        if not self._tap_once():
            self._backoff()
            return
        self._note_sent("klawisz")

    def _start_pair(self):
        first = self._tap_result()
        if first < 0:
            self._ok_held = True
            self._backoff()
            print("OK wciśnięte, bez puszczenia. Puszczam za 5 s.")
            return
        if first == 0:
            self._backoff()
            return
        if self._second_ok():
            self._note_sent("dwa OK")
            return
        self._owe_second_ok = True
        self._backoff()
        if self._ok_held:
            print("Drugie OK wciśnięte, bez puszczenia. Puszczam za 5 s.")
        else:
            print("Jedno OK wyszło, drugie nie. Powtórka drugiego za 5 s.")

    def _second_ok(self):
        gap_ms = config.DOUBLE_OK_GAP_SECONDS * 1000
        time.sleep_ms(gap_ms)
        second = self._tap_result()
        if second == 1:
            return True
        if second < 0:
            self._ok_held = True
            return False
        time.sleep_ms(gap_ms)
        second = self._tap_result()
        if second == 1:
            return True
        if second < 0:
            self._ok_held = True
        return False

    def _send_owed_second(self):
        time.sleep_ms(config.DOUBLE_OK_GAP_SECONDS * 1000)
        result = self._tap_result()
        if result == 1:
            self._owe_second_ok = False
            self._note_sent("drugie OK")
            return
        if result < 0:
            self._ok_held = True
        self._backoff()
        print("Drugie OK nie wyszło. Powtórka za 5 s.")

    def _toggle_mode(self):
        self.mode = _MODE_CONFIRM if self.mode == _MODE_SAFE else _MODE_SAFE
        print("Tryb: %s. Obowiązuje do restartu." % self.mode)

    def _poll_button(self, now):
        down = self.button.value() == 0
        if down != self.last_read_down:
            self.last_read_down = down
            self.last_bounce_ms = now
        # A hold that is already stable still falls through to the long-press
        # check below. Releasing after a long press must not also toggle.
        if (
            time.ticks_diff(now, self.last_bounce_ms) >= config.DEBOUNCE_MS
            and down != self.stable_down
        ):
            self.stable_down = down
            if self.stable_down:
                self.press_started_ms = now
                self.long_press_sent = False
            elif not self.long_press_sent:
                self._toggle_mode()
        if (
            self.stable_down
            and not self.long_press_sent
            and time.ticks_diff(now, self.press_started_ms) >= config.LONG_PRESS_MS
        ):
            self.long_press_sent = True
            if self._confirm_pair():
                if self._owe_second_ok and not self._ok_held:
                    print("Długie naciśnięcie BOOT: wysyłam brakujące drugie OK.")
                else:
                    print("Długie naciśnięcie BOOT: wysyłam dwa OK teraz.")
            else:
                print("Długie naciśnięcie BOOT: wysyłam jeden klawisz teraz.")
            self._send_scheduled()

    def _service_schedule(self, now):
        connected = self.keyboard.connected
        if connected != self.was_connected:
            self.was_connected = connected
            if connected:
                held = self._ok_held
                if held and self.keyboard.release_all():
                    self._ok_held = False
                    if self._confirm_pair():
                        # Releasing the stuck key finishes that OK.
                        # It was the second of a pair, or the first.
                        self._owe_second_ok = not self._owe_second_ok
                elif not held:
                    self.keyboard.release_all()
                try:
                    self.keyboard.pair()
                except OSError as exc:
                    print("Parowanie nie wystartowało: %s" % exc)
                if self._confirm_pair() and (self._owe_second_ok or self._ok_held):
                    self.next_key_at_ms = time.ticks_add(now, 5000)
                    if self._ok_held:
                        print("Połączono. Klawisz jeszcze wciśnięty, puszczam za 5 s.")
                    else:
                        print("Połączono. Brakuje drugiego OK, powtórka za 5 s.")
                else:
                    wait_ms = self._first_key_delay_ms()
                    self.next_key_at_ms = time.ticks_add(now, wait_ms)
                    if config.IMMEDIATE_TEST:
                        print(
                            "Połączono. Pierwszy klawisz za %d s (tryb test, %s)."
                            % (wait_ms // 1000, self.mode)
                        )
                    elif self.mode == _MODE_CONFIRM:
                        print(
                            "Połączono. Dwa OK za %d s, potem dwa OK co %d min."
                            % (wait_ms // 1000, config.KEEPALIVE_INTERVAL_MINUTES)
                        )
                    else:
                        print(
                            "Połączono. Pierwszy klawisz za %d s (tryb cichy)."
                            % (wait_ms // 1000,)
                        )
            else:
                print("Rozłączono. Szukam telewizora.")
        if connected and time.ticks_diff(now, self.next_key_at_ms) >= 0:
            self._send_scheduled()


def main():
    App().run()


if __name__ == "__main__":
    main()
