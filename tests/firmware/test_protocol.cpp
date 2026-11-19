#include <Arduino.h>
#include <array>
#include <cassert>
#include <iostream>

FakeSerial Serial;
unsigned long ticks = 0;
std::array<unsigned int, 32> pins{};
std::array<unsigned int, 32> highs{};

unsigned long millis() { return ticks; }
void pinMode(uint8_t, uint8_t) {}
void digitalWrite(uint8_t pin, uint8_t value) {
  pins[pin] = value;
  highs[pin] += value == HIGH;
}
uint8_t digitalRead(uint8_t pin) { return pins[pin]; }
void analogWrite(uint8_t pin, unsigned int value) { pins[pin] = value; }

#define ENABLE_PIR 1
#include "../../firmware/siteguard_arduino/siteguard_arduino.ino"

void advance(unsigned long elapsed) {
  ticks += elapsed;
  loop();
}

std::string exchange(const std::string& request) {
  Serial.output.clear();
  Serial.input += request + "\n";
  while (Serial.available()) loop();
  return Serial.output;
}

int main() {
  setup();
  assert(pins[LED_PWM_PIN] == 0);
  advance(120);
  pins[PIR_PIN] = HIGH;
  advance(1);
  advance(45);
  assert(exchange("SG1 A0000001 SET_OUTPUT 80 tone_critical") == "SG1 A0000001 ACK 80 tone_critical 1\r\n");
  assert(pins[LED_PWM_PIN] == 204);
  assert(pins[9] == HIGH);
  auto started = highs[9];
  assert(exchange("SG1 A0000001 SET_OUTPUT 80 tone_critical").find(" ACK ") != std::string::npos);
  assert(highs[9] == started);
  assert(exchange("SG1 A0000001 STOP_SOUND").find("ID_REUSED") != std::string::npos);
  assert(exchange("SG1 A0000002 SET_OUTPUT 101 off").find("BAD_ARGS") != std::string::npos);
  assert(exchange("SG1 A0000002 SET_LED -1").find("BAD_ARGS") != std::string::npos);
  assert(exchange("SG1 A0000002 UNKNOWN").find("BAD_COMMAND") != std::string::npos);
  assert(exchange(std::string(115, 'X')).empty());
  advance(1000);
  assert(exchange("SG1 A0000003 PING").find("ACK 80 tone_critical") != std::string::npos);
  advance(2000);
  assert(exchange("SG1 A0000004 GET_STATUS").find("ACK 80 tone_critical") != std::string::npos);
  advance(1501);
  assert(pins[STOP_PIN] == HIGH);
  assert(exchange("SG1 A0000005 GET_STATUS").find("ACK 80 off") != std::string::npos);
  advance(3001);
  assert(pins[LED_PWM_PIN] == 0);
  assert(exchange("SG1 A0000006 GET_STATUS").find("ACK 0 off") != std::string::npos);
  std::cout << "Firmware SG1 framing, ACK, PIR, pulse, duplicate and timeout checks passed\n";
}
