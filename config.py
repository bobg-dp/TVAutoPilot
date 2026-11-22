# Knobs for a caregiver. Edit, then copy this file to the board again.
# HID usages, not the old Arduino key codes. Enter is 0x28. F13 is 0x68.
# The Arduino header called those KEY_RETURN (0xB0) and KEY_F13 (0xF0);
# the library subtracted 136 before putting them in the report.

# How often to send the keep-alive while the TV stays connected.
# In daily use each of these is two OK presses. Ignored for the spacing
# of the test mode below.
KEEPALIVE_INTERVAL_MINUTES = 20

# Daily use, after the TV connects: one OK, so a caregiver can see that
# the remote works and press play. Later keep-alives are two OK presses.
# Ignored when IMMEDIATE_TEST is true.
FIRST_OK_DELAY_SECONDS = 60

# Gap between the two OK presses of a keep-alive. The first can pause
# playback on some sets; the second is the chance to leave it playing.
DOUBLE_OK_GAP_SECONDS = 2

# True = bench test. Single OK a few seconds after the TV connects, then
# again every IMMEDIATE_TEST_INTERVAL_SECONDS. No double press. Leave
# False in daily use.
IMMEDIATE_TEST = False

IMMEDIATE_TEST_DELAY_SECONDS = 5

# Repeat while IMMEDIATE_TEST is True. Ignored in daily use.
IMMEDIATE_TEST_INTERVAL_SECONDS = 30

# Confirm mode. Enter is the TV OK / select key. It dismisses Netflix's
# "Are you still watching?" / "Czy nadal oglądasz?". On some Samsung and
# LG sets the same key pauses playback. Test with a 3 second BOOT press
# during an episode before leaving this mode unattended.
KEY_RETURN = 0x28
CONFIRM_MODE_KEY = KEY_RETURN

# Safe mode. One key that is a real HID report but is not bound by Netflix
# to seek, pause, volume, or focus.
#
# F13 (HID usage 0x68) is the default because:
# - Left/Right seek, Up/Down move focus, media Play and Volume change playback.
# - F13–F24 are not part of the Netflix TV UI.
# - The report map in ble_keyboard.py runs through F24 (usage 0x73). A map
#   that stops at 0x65 makes a strict TV discard F13.
#
# Residual risk, unchanged by the descriptor: some sets only reset the
# Netflix idle timer for keys the app itself handles. An ignored F13 can
# fail to prevent the prompt, and it will not dismiss a prompt that is
# already on screen. Confirm mode exists for that case.
#
# Other keys that also fit the report map and usually do nothing here:
# KEY_F14, KEY_F15, KEY_F16, KEY_SCROLL_LOCK.
# Do not use the arrow keys. Media keys are a different report and are
# rejected below.
KEY_F13 = 0x68
KEY_F14 = 0x69
KEY_F15 = 0x6A
KEY_F16 = 0x6B
KEY_F24 = 0x73
KEY_SCROLL_LOCK = 0x47
SAFE_MODE_KEY = KEY_F13

KEY_LEFT_ARROW = 0x50
KEY_RIGHT_ARROW = 0x4F
KEY_UP_ARROW = 0x52
KEY_DOWN_ARROW = 0x51

# False = boot into confirm mode (Enter). True = boot into safe mode (F13).
# The BOOT button toggles the mode until the next reset or power loss.
# The choice is not stored in flash: after a reboot the device returns to
# this value. If Enter pauses the film, set this to True.
BOOT_INTO_SAFE_MODE = False

# Onboard LED of a typical DOIT ESP32 DevKit V1. Set LED_ACTIVE_HIGH to
# False if the blink pattern looks inverted (lit while it should be dark).
LED_PIN = 2
LED_ACTIVE_HIGH = True

# BOOT button. Active low, external pull-up on the DevKit. Do not move
# this unless the button is wired to another pin: GPIO0 is also a strap
# pin, and holding it during reset enters the ROM download mode.
BUTTON_PIN = 0

LONG_PRESS_MS = 3000
DEBOUNCE_MS = 40

# Hold time for one key tap. Some TV HID stacks miss a shorter press.
KEY_HOLD_MS = 80

# Shown in the TV's Bluetooth list. 15 characters maximum.
DEVICE_NAME = "TVAutoPilot"

_ARROW_KEYS = {
    KEY_LEFT_ARROW: "Left arrow seeks on Netflix",
    KEY_RIGHT_ARROW: "Right arrow seeks on Netflix",
    KEY_UP_ARROW: "Up arrow moves focus on Netflix",
    KEY_DOWN_ARROW: "Down arrow moves focus on Netflix",
}


def _check_range(name, value, low, high):
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise ValueError("%s must be an integer from %s to %s" % (name, low, high))


def _check_bool(name, value):
    # 0 and 1 are accepted so a caregiver can keep the old on/off habit.
    if isinstance(value, bool) or value in (0, 1):
        return
    raise ValueError("%s must be True or False" % name)


def _check_key(name, value):
    _check_range(name, value, 1, KEY_F24)
    reason = _ARROW_KEYS.get(value)
    if reason:
        raise ValueError("%s: %s" % (name, reason))


def validate():
    _check_range("KEEPALIVE_INTERVAL_MINUTES", KEEPALIVE_INTERVAL_MINUTES, 1, 24 * 60)
    _check_range("FIRST_OK_DELAY_SECONDS", FIRST_OK_DELAY_SECONDS, 1, 600)
    _check_range("DOUBLE_OK_GAP_SECONDS", DOUBLE_OK_GAP_SECONDS, 1, 10)
    _check_range("IMMEDIATE_TEST_DELAY_SECONDS", IMMEDIATE_TEST_DELAY_SECONDS, 1, 60)
    _check_range("IMMEDIATE_TEST_INTERVAL_SECONDS", IMMEDIATE_TEST_INTERVAL_SECONDS, 5, 600)
    _check_range("KEY_HOLD_MS", KEY_HOLD_MS, 20, 500)
    _check_range("LONG_PRESS_MS", LONG_PRESS_MS, 500, 10000)
    _check_range("DEBOUNCE_MS", DEBOUNCE_MS, 1, 500)
    _check_range("LED_PIN", LED_PIN, 0, 39)
    _check_range("BUTTON_PIN", BUTTON_PIN, 0, 39)
    _check_bool("LED_ACTIVE_HIGH", LED_ACTIVE_HIGH)
    _check_bool("BOOT_INTO_SAFE_MODE", BOOT_INTO_SAFE_MODE)
    _check_bool("IMMEDIATE_TEST", IMMEDIATE_TEST)
    _check_key("CONFIRM_MODE_KEY", CONFIRM_MODE_KEY)
    _check_key("SAFE_MODE_KEY", SAFE_MODE_KEY)
    if not isinstance(DEVICE_NAME, str) or not 1 <= len(DEVICE_NAME.encode("utf-8")) <= 15:
        raise ValueError("DEVICE_NAME must be 1 to 15 bytes")


validate()
