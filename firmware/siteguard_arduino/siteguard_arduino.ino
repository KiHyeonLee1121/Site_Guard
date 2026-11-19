#include <Arduino.h>
#include <stdlib.h>
#include <string.h>

// Logic signals to external drivers. Set ENABLE_PIR after wiring the sensor.
#ifndef ENABLE_PIR
#define ENABLE_PIR 0
#endif
constexpr uint8_t PIR_PIN = 2;
constexpr uint8_t LED_PWM_PIN = 5;
constexpr uint8_t SOUND_PINS[] = {6, 7, 8, 9};
constexpr uint8_t STOP_PIN = 10;
constexpr unsigned long WATCHDOG_MS = 3000;
constexpr unsigned long TRIGGER_MS = 100;
constexpr unsigned long INTERLOCK_MS = 40;
constexpr unsigned long SOUND_LIMIT_MS = 4500;
constexpr unsigned long PIR_DEBOUNCE_MS = 40;
constexpr char const *SOUND_NAMES[] = {"off", "voice_warning", "voice_critical", "tone_warning", "tone_critical"};

char line[96];
char lastRequest[96] = {};
char lastId[9] = {};
size_t lineLength = 0;
bool overflowed = false;
uint8_t brightness = 0;
uint8_t sound = 0;
uint8_t pendingSound = 0;
uint8_t activePin = 0;
unsigned long pinSince = 0;
unsigned long soundSince = 0;
unsigned long lastContact = 0;
bool connected = false;
bool pir = false;
bool pirRaw = false;
unsigned long pirChanged = 0;

void pulse(uint8_t pin) {
  if (activePin) digitalWrite(activePin, LOW);
  activePin = pin;
  pinSince = millis();
  digitalWrite(pin, HIGH);
}

void setLed(uint8_t level) {
  brightness = level;
  analogWrite(LED_PWM_PIN, (static_cast<unsigned int>(level) * 255 + 50) / 100);
}

void setSound(uint8_t next) {
  if (sound || pendingSound || next == 0) {
    sound = 0;
    pendingSound = next;
    pulse(STOP_PIN);
  } else if (activePin == STOP_PIN) {
    pendingSound = next;
  } else {
    sound = next;
    soundSince = millis();
    pulse(SOUND_PINS[sound - 1]);
  }
}

void allOff() {
  setLed(0);
  setSound(0);
}

bool validId(const char *id) {
  return id && strlen(id) == 8 && strspn(id, "0123456789ABCDEF") == 8;
}

void nack(const char *id, const char *code) {
  Serial.print("SG1 ");
  Serial.print(id);
  Serial.print(" NACK ");
  Serial.println(code);
}

void ack(const char *id) {
  Serial.print("SG1 ");
  Serial.print(id);
  Serial.print(" ACK ");
  Serial.print(brightness);
  Serial.print(' ');
  Serial.print(SOUND_NAMES[sound]);
  Serial.print(' ');
  if (ENABLE_PIR) Serial.println(pir ? "1" : "0");
  else Serial.println("-");
}

int integerLevel(const char *text) {
  if (!text || !*text || strlen(text) > 3 || strspn(text, "0123456789") != strlen(text)) return -1;
  int value = atoi(text);
  return value <= 100 ? value : -1;
}

int lookupSound(const char *text) {
  if (!text) return -1;
  for (unsigned int i = 0; i < sizeof(SOUND_NAMES) / sizeof(SOUND_NAMES[0]); ++i) {
    if (strcmp(text, SOUND_NAMES[i]) == 0) return i;
  }
  return -1;
}

void handleLine(char *text) {
  char original[sizeof(line)];
  strcpy(original, text);
  char *cursor;
  char *version = strtok_r(text, " ", &cursor);
  char *id = strtok_r(nullptr, " ", &cursor);
  if (!version || strcmp(version, "SG1") || !validId(id)) return;
  if (strcmp(id, lastId) == 0) {
    if (strcmp(original, lastRequest) == 0) {
      lastContact = millis();
      connected = true;
      ack(id);
    } else {
      nack(id, "ID_REUSED");
    }
    return;
  }
  char *cmd = strtok_r(nullptr, " ", &cursor);
  char *first = strtok_r(nullptr, " ", &cursor);
  char *second = strtok_r(nullptr, " ", &cursor);
  char *extra = strtok_r(nullptr, " ", &cursor);
  if (!cmd || extra) { nack(id, "BAD_ARGS"); return; }
  if (strcmp(cmd, "SET_OUTPUT") == 0) {
    int led = integerLevel(first), audio = lookupSound(second);
    if (led < 0 || audio < 0) { nack(id, "BAD_ARGS"); return; }
    setLed(led);
    setSound(audio);
  } else if (strcmp(cmd, "SET_LED") == 0) {
    int led = integerLevel(first);
    if (led < 0 || second) { nack(id, "BAD_ARGS"); return; }
    setLed(led);
  } else if (strcmp(cmd, "PLAY_SOUND") == 0) {
    int audio = lookupSound(first);
    if (audio < 0 || second) { nack(id, "BAD_ARGS"); return; }
    setSound(audio);
  } else if (strcmp(cmd, "ALL_OFF") == 0 || strcmp(cmd, "STOP_SOUND") == 0 ||
             strcmp(cmd, "GET_STATUS") == 0 || strcmp(cmd, "PING") == 0) {
    if (first) { nack(id, "BAD_ARGS"); return; }
    if (strcmp(cmd, "ALL_OFF") == 0) allOff();
    if (strcmp(cmd, "STOP_SOUND") == 0) setSound(0);
  } else {
    nack(id, "BAD_COMMAND");
    return;
  }
  strcpy(lastId, id);
  strcpy(lastRequest, original);
  lastContact = millis();
  connected = true;
  ack(id);
}

void setup() {
  pinMode(PIR_PIN, INPUT_PULLDOWN);
  pinMode(LED_PWM_PIN, OUTPUT);
  for (auto pin : SOUND_PINS) {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, LOW);
  }
  pinMode(STOP_PIN, OUTPUT);
  digitalWrite(STOP_PIN, LOW);
  allOff();
  Serial.begin(115200);
}

void loop() {
  unsigned long now = millis();
  if (connected && now - lastContact >= WATCHDOG_MS) {
    connected = false;
    allOff();
  }
  if (sound && now - soundSince >= SOUND_LIMIT_MS) setSound(0);
  if (activePin && now - pinSince >= TRIGGER_MS) {
    digitalWrite(activePin, LOW);
    activePin = 0;
    pinSince = now;
  }
  if (pendingSound && connected && !activePin && now - pinSince >= INTERLOCK_MS) {
    sound = pendingSound;
    pendingSound = 0;
    soundSince = now;
    pulse(SOUND_PINS[sound - 1]);
  }
  if (ENABLE_PIR) {
    bool value = digitalRead(PIR_PIN) == HIGH;
    if (value != pirRaw) { pirRaw = value; pirChanged = now; }
    if (now - pirChanged >= PIR_DEBOUNCE_MS) pir = pirRaw;
  }
  // Bound bytes handled per iteration so framing errors cannot delay the watchdog.
  for (int i = 0; i < 64 && Serial.available(); ++i) {
    char ch = Serial.read();
    if (ch == '\n') {
      if (!overflowed && lineLength) {
        line[lineLength] = '\0';
        handleLine(line);
      }
      lineLength = 0;
      overflowed = false;
    } else if (ch != '\r' && !overflowed) {
      if (ch < 32 || ch > 126 || lineLength >= sizeof(line) - 1) overflowed = true;
      else line[lineLength++] = ch;
    }
  }
}
