# TVAutoPilot
#
# An ESP32 that stays paired as a BLE HID keyboard and, on a timer, sends
# one key so Netflix does not stop on "Are you still watching?".
#
# Confirm mode (default): Enter / OK. This dismisses the prompt. On some
# TVs it also pauses playback, so it has to be tried with a long BOOT
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
        self._first_ok_pending = not config.IMMEDIATE_TEST
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

    def _tap_once(self):
        if not self.keyboard.connected:
            print("Nie wysłano: telewizor nie jest połączony.")
            return False
        if not self.keyboard.tap(self._active_key(), config.KEY_HOLD_MS):
            print("Nie wysłano: telewizor odrzucił raport.")
            return False
        self.flash_until_ms = time.ticks_add(time.ticks_ms(), 160)
        return True

    def _note_sent(self, what):
        self.next_key_at_ms = time.ticks_add(time.ticks_ms(), self._interval_ms())
        print(
            "Wysłano %s 0x%02X (tryb %s). Następny za %s."
            % (what, self._active_key(), self.mode, self._interval_label())
        )

    def _backoff(self):
        self.next_key_at_ms = time.ticks_add(time.ticks_ms(), 5000)

    # Test mode stays a single key on the short interval.
    # Daily confirm mode: the first press after a connection is one OK.
    # Every later keep-alive is two OK presses, so a set that pauses on
    # Enter still gets a second press.
    def _send_scheduled(self):
        single = (
            config.IMMEDIATE_TEST
            or self._first_ok_pending
            or self.mode != _MODE_CONFIRM
        )
        if not self._tap_once():
            self._backoff()
            return
        if single:
            if self._first_ok_pending and not config.IMMEDIATE_TEST:
                self._first_ok_pending = False
                what = "jedno OK" if self.mode == _MODE_CONFIRM else "klawisz"
                self._note_sent(what)
            else:
                self._note_sent("klawisz")
            return
        time.sleep_ms(config.DOUBLE_OK_GAP_SECONDS * 1000)
        if not self._tap_once():
            self._note_sent("jedno OK, drugie nie wyszło")
            return
        self._note_sent("dwa OK")

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
            print("Długie naciśnięcie BOOT: wysyłam jeden klawisz teraz.")
            self._tap_once()

    def _service_schedule(self, now):
        connected = self.keyboard.connected
        if connected != self.was_connected:
            self.was_connected = connected
            if connected:
                self.keyboard.release_all()
                try:
                    self.keyboard.pair()
                except OSError as exc:
                    print("Parowanie nie wystartowało: %s" % exc)
                self._first_ok_pending = not config.IMMEDIATE_TEST
                wait_ms = self._first_key_delay_ms()
                self.next_key_at_ms = time.ticks_add(now, wait_ms)
                if config.IMMEDIATE_TEST:
                    print(
                        "Połączono. Pierwszy klawisz za %d s (tryb test, %s)."
                        % (wait_ms // 1000, self.mode)
                    )
                elif self.mode == _MODE_CONFIRM:
                    print(
                        "Połączono. Jedno OK za %d s, potem dwa OK co %d min."
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
