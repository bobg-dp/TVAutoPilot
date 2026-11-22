// TVAutoPilot
//
// An ESP32 that stays paired as a BLE HID keyboard and, on a timer, sends
// one key so Netflix does not stop on "Are you still watching?".
//
// Confirm mode (default): Enter / OK. This dismisses the prompt. On some
// TVs it also pauses playback, so it has to be tried with a long BOOT
// press before it is left running.
//
// Safe mode: the single key in include/config.h, default F13. Netflix does
// not bind F13 to seek, pause, or volume. It may also fail to count F13 as
// activity. See config.h.
//
// The loop never deep-sleeps and never light-sleeps. Either one drops the
// Bluetooth link, and the TV would have to pair again. The radio stays up
// for as long as the board has USB power.

#include <Arduino.h>
#include <BleKeyboard.h>

#include "config.h"

static_assert(KEEPALIVE_INTERVAL_MINUTES >= 1,
              "KEEPALIVE_INTERVAL_MINUTES must be at least 1");
static_assert(KEEPALIVE_INTERVAL_MINUTES <= 24 * 60,
              "KEEPALIVE_INTERVAL_MINUTES is too large");
static_assert(STARTUP_DELAY_MINUTES >= 0, "STARTUP_DELAY_MINUTES must be >= 0");
static_assert(STARTUP_DELAY_MINUTES <= 24 * 60,
              "STARTUP_DELAY_MINUTES is too large");
static_assert(KEY_HOLD_MS >= 20 && KEY_HOLD_MS <= 500, "KEY_HOLD_MS out of range");
static_assert(LONG_PRESS_MS >= 500, "LONG_PRESS_MS is too short to tell from a tap");

// Arrows seek or move focus on Netflix. Reject them at compile time so a
// config edit cannot turn the keep-alive into a seek or a focus change.
static_assert(SAFE_MODE_KEY != KEY_LEFT_ARROW, "Left arrow seeks on Netflix");
static_assert(SAFE_MODE_KEY != KEY_RIGHT_ARROW, "Right arrow seeks on Netflix");
static_assert(SAFE_MODE_KEY != KEY_UP_ARROW, "Up arrow moves focus on Netflix");
static_assert(SAFE_MODE_KEY != KEY_DOWN_ARROW, "Down arrow moves focus on Netflix");
static_assert(CONFIRM_MODE_KEY != KEY_LEFT_ARROW, "Left arrow seeks on Netflix");
static_assert(CONFIRM_MODE_KEY != KEY_RIGHT_ARROW, "Right arrow seeks on Netflix");
static_assert(CONFIRM_MODE_KEY != KEY_UP_ARROW, "Up arrow moves focus on Netflix");
static_assert(CONFIRM_MODE_KEY != KEY_DOWN_ARROW, "Down arrow moves focus on Netflix");

enum class Mode : uint8_t { Confirm, Safe };

static BleKeyboard bleKeyboard(DEVICE_NAME, "TVAutoPilot", 100);

static Mode mode = Mode::Confirm;
static bool wasConnected = false;
static bool stableDown = false;
static bool lastReadDown = false;
static bool longPressSent = false;
static uint32_t lastBounceMs = 0;
static uint32_t pressStartedMs = 0;
static uint32_t nextKeyAtMs = 0;
static uint32_t flashUntilMs = 0;

static uint32_t intervalMs() {
  return (uint32_t)KEEPALIVE_INTERVAL_MINUTES * 60000UL;
}

static uint32_t firstKeyDelayMs() {
  if (IMMEDIATE_TEST) {
    return (uint32_t)IMMEDIATE_TEST_DELAY_SECONDS * 1000UL;
  }
  return (uint32_t)STARTUP_DELAY_MINUTES * 60000UL;
}

static void writeLed(bool on) {
#if LED_ACTIVE_HIGH
  digitalWrite(LED_PIN, on ? HIGH : LOW);
#else
  digitalWrite(LED_PIN, on ? LOW : HIGH);
#endif
}

// Advertising: slow blink. Confirm is one flash, safe is two, so the mode
// is visible before the TV connects.
// Connected: solid. Safe mode dips the LED twice every 3 s so a solid lamp
// still tells the modes apart from across the room.
// A key send inverts the pattern for a short window (the "brief flash").
static bool patternOn(uint32_t now, bool connected) {
  if (!connected) {
    const uint32_t t = now % 2000UL;
    if (mode == Mode::Confirm) {
      return t < 180;
    }
    return t < 140 || (t >= 280 && t < 420);
  }
  if (mode == Mode::Confirm) {
    return true;
  }
  const uint32_t t = now % 3000UL;
  const bool dip = t < 70 || (t >= 160 && t < 230);
  return !dip;
}

static void applyLed(uint32_t now) {
  bool on = patternOn(now, bleKeyboard.isConnected());
  if ((int32_t)(flashUntilMs - now) > 0) {
    on = !on;
  }
  writeLed(on);
}

static const char* modeName() {
  return mode == Mode::Safe ? "cichy" : "potwierdzenie";
}

// Press and release the key for the active mode. Returns false when the
// TV is not connected, so a test press cannot look like it succeeded.
static bool sendKeepAlive() {
  if (!bleKeyboard.isConnected()) {
    Serial.println("Nie wysłano: telewizor nie jest połączony.");
    return false;
  }

  const uint8_t key = (mode == Mode::Safe) ? SAFE_MODE_KEY : CONFIRM_MODE_KEY;
  bleKeyboard.press(key);
  delay(KEY_HOLD_MS);
  // releaseAll also clears a modifier, in case a future key code uses one.
  bleKeyboard.releaseAll();

  const uint32_t now = millis();
  flashUntilMs = now + 160;
  nextKeyAtMs = now + intervalMs();
  Serial.printf("Wysłano klawisz 0x%02X (tryb %s). Następny za %u min.\n",
                key,
                modeName(),
                (unsigned)KEEPALIVE_INTERVAL_MINUTES);
  return true;
}

static void toggleMode() {
  mode = (mode == Mode::Safe) ? Mode::Confirm : Mode::Safe;
  Serial.printf("Tryb: %s. Obowiązuje do restartu.\n", modeName());
}

static void pollButton(uint32_t now) {
  const bool down = digitalRead(BUTTON_PIN) == LOW;
  if (down != lastReadDown) {
    lastReadDown = down;
    lastBounceMs = now;
  }
  // A hold that is already stable still falls through to the long-press
  // check below. Releasing after a long press must not also toggle.
  if ((uint32_t)(now - lastBounceMs) >= DEBOUNCE_MS && down != stableDown) {
    stableDown = down;
    if (stableDown) {
      pressStartedMs = now;
      longPressSent = false;
    } else if (!longPressSent) {
      toggleMode();
    }
  }

  if (stableDown && !longPressSent &&
      (uint32_t)(now - pressStartedMs) >= LONG_PRESS_MS) {
    longPressSent = true;
    Serial.println("Długie naciśnięcie BOOT: wysyłam klawisz teraz.");
    sendKeepAlive();
  }
}

static void serviceSchedule(uint32_t now) {
  const bool connected = bleKeyboard.isConnected();
  if (connected != wasConnected) {
    wasConnected = connected;
    if (connected) {
      // Drop anything that was logically held across the previous link.
      bleKeyboard.releaseAll();
      const uint32_t waitMs = firstKeyDelayMs();
      nextKeyAtMs = now + waitMs;
      Serial.printf("Połączono. Pierwszy klawisz za %lu s (tryb %s).\n",
                    (unsigned long)(waitMs / 1000UL),
                    modeName());
    } else {
      Serial.println("Rozłączono. Szukam telewizora.");
    }
  }

  if (connected && (int32_t)(now - nextKeyAtMs) >= 0) {
    sendKeepAlive();
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  writeLed(false);

#if BOOT_INTO_SAFE_MODE
  mode = Mode::Safe;
#else
  mode = Mode::Confirm;
#endif

  // VID/PID stay at the library defaults. Those values are what this stack
  // has actually been paired as on Android-based TVs; swapping in a custom
  // id is more likely to make a set ignore the keyboard.
  bleKeyboard.begin();

  Serial.println("TVAutoPilot");
  Serial.printf("Tryb po starcie: %s. Odstęp: %u min.\n",
                modeName(),
                (unsigned)KEEPALIVE_INTERVAL_MINUTES);
  Serial.println("Krótkie BOOT: zmiana trybu. Przytrzymanie ok. 3 s: wyślij teraz.");
  Serial.println("Szukam telewizora. Na liście Bluetooth: TVAutoPilot.");
}

void loop() {
  const uint32_t now = millis();
  pollButton(now);
  serviceSchedule(now);
  applyLed(now);
  // Yield so the idle task can run. Do not replace this with deep sleep
  // or light sleep: the BLE connection would drop.
  delay(10);
}
