#ifndef error_h
#define error_h

#include "header.h"

void fatalBlink();
void errorFlash(const __FlashStringHelper* msg);

// Error messages stored in flash.
#define error(msg) errorFlash(F(msg))

#endif // error_h
