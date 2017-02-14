#include "error.h"

void fatalBlink() {
  while (true) {
    if (ERROR_LED_PIN >= 0) {
      digitalWrite(ERROR_LED_PIN, HIGH);
      delay(200);
      digitalWrite(ERROR_LED_PIN, LOW);
      delay(200);
    }
  }
}

void errorFlash(const __FlashStringHelper* msg) {
  sd.errorPrint(msg);
  fatalBlink();
}
