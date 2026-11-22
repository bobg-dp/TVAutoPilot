#pragma once

#include <Arduino.h>

// Knobs for a caregiver. Edit, then flash again with: pio run -t upload
// Names such as KEY_F13 and KEY_RETURN come from the BLE keyboard library.

#include <BleKeyboard.h>

// HID Scroll Lock (usage 0x47). The library header does not name it.
// Arduino's non-printing key code is usage + 136, which is 0xCF.
// Not the default: a few Android TV builds toast "Scroll Lock".
#ifndef KEY_SCROLL_LOCK
#define KEY_SCROLL_LOCK 0xCF
#endif

// How often to send the keep-alive while the TV stays connected.
#ifndef KEEPALIVE_INTERVAL_MINUTES
#define KEEPALIVE_INTERVAL_MINUTES 20
#endif

// Wait this long after each new Bluetooth connection before the first
// automatic key. The default matches the interval, so pairing itself
// does not press a key. Ignored when IMMEDIATE_TEST is 1.
#ifndef STARTUP_DELAY_MINUTES
#define STARTUP_DELAY_MINUTES 20
#endif

// 1 = a few seconds after the TV connects, send the current key once.
// For a bench test. Leave 0 in daily use. A long BOOT press is the
// other way to send a key immediately, and it needs no reflash.
#ifndef IMMEDIATE_TEST
#define IMMEDIATE_TEST 0
#endif

#ifndef IMMEDIATE_TEST_DELAY_SECONDS
#define IMMEDIATE_TEST_DELAY_SECONDS 5
#endif

// Confirm mode. Enter is the TV OK / select key. It dismisses Netflix's
// "Are you still watching?" / "Czy nadal oglądasz?". On some Samsung and
// LG sets the same key pauses playback. Test with a 3 second BOOT press
// during an episode before leaving this mode unattended.
#ifndef CONFIRM_MODE_KEY
#define CONFIRM_MODE_KEY KEY_RETURN
#endif

// Safe mode. One key that is a real HID report but is not bound by Netflix
// to seek, pause, volume, or focus.
//
// F13 (library code KEY_F13, HID usage 0x68) is the default because:
// - Left/Right seek, Up/Down move focus, media Play and Volume change playback.
// - F13–F24 are not part of the Netflix TV UI.
// - The vendored library extends the HID report map through F24. Upstream
//   stopped at usage 0x65, so a strict TV would have discarded F13.
//
// Residual risk, unchanged by the descriptor fix: some sets only reset the
// Netflix idle timer for keys the app itself handles. An ignored F13 can
// fail to prevent the prompt, and it will not dismiss a prompt that is
// already on screen. Confirm mode exists for that case.
//
// Other keys that also fit the report map and usually do nothing here:
// KEY_F14, KEY_F15, KEY_F16, KEY_SCROLL_LOCK.
// Do not use KEY_LEFT_ARROW, KEY_RIGHT_ARROW, KEY_UP_ARROW, KEY_DOWN_ARROW,
// or media keys (those are a different type and will not compile here).
#ifndef SAFE_MODE_KEY
#define SAFE_MODE_KEY KEY_F13
#endif

// 0 = boot into confirm mode (Enter). 1 = boot into safe mode (F13).
// The BOOT button toggles the mode until the next reset or power loss.
// There is no Wi-Fi and the choice is not stored in flash: after a reboot
// the device returns to this value. If Enter pauses the film, set this to 1.
#ifndef BOOT_INTO_SAFE_MODE
#define BOOT_INTO_SAFE_MODE 0
#endif

// Onboard LED of a typical DOIT ESP32 DevKit V1. Set LED_ACTIVE_HIGH to 0
// if the blink pattern looks inverted (lit while it should be dark).
#ifndef LED_PIN
#define LED_PIN 2
#endif

#ifndef LED_ACTIVE_HIGH
#define LED_ACTIVE_HIGH 1
#endif

// BOOT button. Active low, external pull-up on the DevKit. Do not move
// this unless the button is wired to another pin: GPIO0 is also a strap
// pin, and holding it during reset enters the ROM download mode.
#ifndef BUTTON_PIN
#define BUTTON_PIN 0
#endif

#ifndef LONG_PRESS_MS
#define LONG_PRESS_MS 3000
#endif

#ifndef DEBOUNCE_MS
#define DEBOUNCE_MS 40
#endif

// Hold time for one key tap. Some TV HID stacks miss a shorter press.
#ifndef KEY_HOLD_MS
#define KEY_HOLD_MS 80
#endif

// Shown in the TV's Bluetooth list. 15 characters maximum (library limit).
#ifndef DEVICE_NAME
#define DEVICE_NAME "TVAutoPilot"
#endif
