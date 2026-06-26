#include <Arduino.h>
#include <Adafruit_NeoPixel.h>

#define LED_PIN 16

#define ROW0 0
#define ROW1 1
#define ROW2 2
#define COL0 3
#define COL1 6
#define COL2 7

#define MAX_DIN 12
#define MAX_CS 11
#define MAX_CLK 10

#define ENC_A 26
#define ENC_B 27
#define ENC_BTN 28

#define REG_DECODE 0x09
#define REG_INTENSITY 0x0A
#define REG_SCANLIMIT 0x0B
#define REG_SHUTDOWN 0x0C
#define REG_DISPLAYTEST 0x0F
#define REG_DIGIT0 0x01

const uint8_t ROWS[3] = {ROW0, ROW1, ROW2};
const uint8_t COLS[3] = {COL0, COL1, COL2};

const unsigned long BUTTON_DEBOUNCE_MS = 20;
const unsigned long ENCODER_DEBOUNCE_US = 700;

bool keyStable[9] = {false};
bool keyRaw[9] = {false};
unsigned long keyChangedAt[9] = {0};

volatile int encDelta = 0;
volatile bool encAPrev = HIGH;
volatile unsigned long encLastUs = 0;

bool encBtnStable = false;
bool encBtnRaw = false;
unsigned long encBtnChangedAt = 0;

uint8_t framebuf[8] = {0};

Adafruit_NeoPixel led(1, LED_PIN, NEO_GRB + NEO_KHZ800);
uint8_t ledR = 255;
uint8_t ledG = 255;
uint8_t ledB = 255;
uint8_t ledBrightness = 255;

void ledApply() {
  float scale = ledBrightness / 255.0f;
  led.setPixelColor(0, led.Color(
    (uint8_t)(ledR * scale),
    (uint8_t)(ledG * scale),
    (uint8_t)(ledB * scale)
  ));
  led.show();
}

void maxWrite(uint8_t reg, uint8_t data) {
  digitalWrite(MAX_CS, LOW);
  shiftOut(MAX_DIN, MAX_CLK, MSBFIRST, reg);
  shiftOut(MAX_DIN, MAX_CLK, MSBFIRST, data);
  digitalWrite(MAX_CS, HIGH);
}

void maxFlush() {
  for (uint8_t row = 0; row < 8; row++) {
    maxWrite(REG_DIGIT0 + row, framebuf[row]);
  }
}

void maxInit() {
  maxWrite(REG_DECODE, 0x00);
  maxWrite(REG_SCANLIMIT, 0x07);
  maxWrite(REG_INTENSITY, 0x04);
  maxWrite(REG_SHUTDOWN, 0x01);
  maxWrite(REG_DISPLAYTEST, 0x00);
}

void maxClear() {
  memset(framebuf, 0, 8);
  maxFlush();
}

void setPixel(uint8_t n, bool on) {
  if (n > 63) {
    return;
  }
  uint8_t row = n / 8;
  uint8_t bit = 7 - (n % 8);
  if (on) {
    framebuf[row] |= (1 << bit);
  } else {
    framebuf[row] &= ~(1 << bit);
  }
}

void encoderISR() {
  unsigned long now = micros();
  if (now - encLastUs < ENCODER_DEBOUNCE_US) {
    return;
  }
  bool a = digitalRead(ENC_A);
  bool b = digitalRead(ENC_B);
  if (a != encAPrev) {
    encDelta += (a != b) ? 1 : -1;
    encAPrev = a;
    encLastUs = now;
  }
}

void ltrim(String &s) {
  while (s.length() > 0 && s[0] == ' ') {
    s.remove(0, 1);
  }
}

bool isNumber(const String &s) {
  if (s.length() == 0) {
    return false;
  }
  for (uint16_t i = 0; i < s.length(); i++) {
    if (!isDigit(s[i])) {
      return false;
    }
  }
  return true;
}

bool isHexColor(const String &s) {
  if (s.length() != 6) {
    return false;
  }
  for (uint8_t i = 0; i < 6; i++) {
    if (!isHexadecimalDigit(s[i])) {
      return false;
    }
  }
  return true;
}

void applyHumanReadablePixels(const String &list) {
  memset(framebuf, 0, 8);
  String rest = list;
  while (rest.length() > 0) {
    int comma = rest.indexOf(',');
    String token = comma < 0 ? rest : rest.substring(0, comma);
    rest = comma < 0 ? "" : rest.substring(comma + 1);
    token.trim();
    if (isNumber(token)) {
      int n = token.toInt();
      if (n >= 0 && n <= 63) {
        setPixel((uint8_t)n, true);
      }
    }
  }
  maxFlush();
}

void handleCommand(const String &line) {
  int split = line.indexOf(' ');
  String verb = split < 0 ? line : line.substring(0, split);
  String rest = split < 0 ? "" : line.substring(split + 1);
  ltrim(rest);
  verb.toLowerCase();

  if (verb == "clear") {
    maxClear();
  } else if (verb == "bright") {
    maxWrite(REG_INTENSITY, (uint8_t)constrain(rest.toInt(), 0, 15));
  } else if (verb == "pixel") {
    int space = rest.indexOf(' ');
    if (space > 0) {
      int n = rest.substring(0, space).toInt();
      bool value = rest.substring(space + 1).toInt() != 0;
      if (n >= 0 && n <= 63) {
        setPixel((uint8_t)n, value);
        maxFlush();
      }
    }
  } else if (verb == "pixels") {
    bool humanReadable = false;
    if (rest.startsWith("-h ") || rest.startsWith("--human-readable ")) {
      humanReadable = true;
      rest = rest.substring(rest.indexOf(' ') + 1);
      ltrim(rest);
    }
    if (humanReadable) {
      applyHumanReadablePixels(rest);
    } else if (rest.length() >= 64) {
      for (uint8_t n = 0; n < 64; n++) {
        setPixel(n, rest[n] == '1');
      }
      maxFlush();
    }
  } else if (verb == "led") {
    if (rest.startsWith("-c ")) {
      String hex = rest.substring(3);
      hex.trim();
      if (isHexColor(hex)) {
        ledR = (uint8_t)strtol(hex.substring(0, 2).c_str(), NULL, 16);
        ledG = (uint8_t)strtol(hex.substring(2, 4).c_str(), NULL, 16);
        ledB = (uint8_t)strtol(hex.substring(4, 6).c_str(), NULL, 16);
        ledApply();
      }
    } else if (rest.startsWith("-b ")) {
      int percent = constrain(rest.substring(3).toInt(), 0, 100);
      ledBrightness = (uint8_t)(percent / 100.0f * 255);
      ledApply();
    }
  } else if (verb == "ping") {
    Serial.println("pong");
  }
}

void emitButton(uint8_t index, bool pressed) {
  Serial.print("BTN:");
  Serial.print(index);
  Serial.print(":");
  Serial.println(pressed ? "P" : "R");
}

void scanButtons() {
  unsigned long now = millis();
  for (int row = 0; row < 3; row++) {
    digitalWrite(ROWS[row], LOW);
    delayMicroseconds(10);
    for (int col = 0; col < 3; col++) {
      uint8_t index = row * 3 + col;
      bool pressed = digitalRead(COLS[col]) == LOW;
      if (pressed != keyRaw[index]) {
        keyRaw[index] = pressed;
        keyChangedAt[index] = now;
      }
      if (pressed != keyStable[index] && now - keyChangedAt[index] >= BUTTON_DEBOUNCE_MS) {
        keyStable[index] = pressed;
        emitButton(index, pressed);
      }
    }
    digitalWrite(ROWS[row], HIGH);
  }
}

void scanEncoderButton() {
  unsigned long now = millis();
  bool pressed = digitalRead(ENC_BTN) == LOW;
  if (pressed != encBtnRaw) {
    encBtnRaw = pressed;
    encBtnChangedAt = now;
  }
  if (pressed != encBtnStable && now - encBtnChangedAt >= BUTTON_DEBOUNCE_MS) {
    encBtnStable = pressed;
    Serial.print("ENCBTN:");
    Serial.println(pressed ? "P" : "R");
  }
}

void drainEncoder() {
  noInterrupts();
  int delta = encDelta;
  encDelta = 0;
  interrupts();

  while (delta != 0) {
    Serial.println(delta > 0 ? "ENC:+1" : "ENC:-1");
    delta += delta > 0 ? -1 : 1;
  }
}

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(20);

  for (int row = 0; row < 3; row++) {
    pinMode(ROWS[row], OUTPUT);
    digitalWrite(ROWS[row], HIGH);
  }
  for (int col = 0; col < 3; col++) {
    pinMode(COLS[col], INPUT_PULLUP);
  }

  pinMode(MAX_DIN, OUTPUT);
  pinMode(MAX_CS, OUTPUT);
  pinMode(MAX_CLK, OUTPUT);
  digitalWrite(MAX_CS, HIGH);
  maxInit();
  maxClear();

  led.begin();
  led.setBrightness(255);
  ledApply();

  pinMode(ENC_A, INPUT_PULLUP);
  pinMode(ENC_B, INPUT_PULLUP);
  pinMode(ENC_BTN, INPUT_PULLUP);
  encAPrev = digitalRead(ENC_A);
  attachInterrupt(digitalPinToInterrupt(ENC_A), encoderISR, CHANGE);
}

void loop() {
  scanButtons();
  drainEncoder();
  scanEncoderButton();

  while (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) {
      handleCommand(line);
    }
  }

  delay(1);
}
