#pragma once

#include <cstdint>
#include <string>

using std::uint8_t;
constexpr uint8_t LOW = 0;
constexpr uint8_t HIGH = 1;
constexpr uint8_t OUTPUT = 1;
constexpr uint8_t INPUT_PULLDOWN = 2;

struct FakeSerial {
  std::string input;
  std::string output;

  void begin(int) {}
  int available() { return !input.empty(); }
  char read() {
    char c = input.front();
    input.erase(0, 1);
    return c;
  }
  void print(const char* value) { output += value; }
  void print(char value) { output += value; }
  void print(uint8_t value) { output += std::to_string(value); }
  void println(const char* value) { output += std::string(value) + "\r\n"; }
};

extern FakeSerial Serial;
unsigned long millis();
void pinMode(uint8_t, uint8_t);
void digitalWrite(uint8_t pin, uint8_t value);
uint8_t digitalRead(uint8_t pin);
void analogWrite(uint8_t pin, unsigned int value);
