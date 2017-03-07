#include "globals.h"

SdFat sd;
SdBaseFile binFile;
Bounce debouncer = Bounce();
char binName[13] = FILE_BASE_NAME "00.bin";

block_t* emptyQueue[QUEUE_DIM];
uint8_t emptyHead;
uint8_t emptyTail;

block_t* fullQueue[QUEUE_DIM];
volatile uint8_t fullHead;  // volatile insures non-interrupt code sees changes.
uint8_t fullTail;

// Pointer to current buffer.
block_t* isrBuf;

// Need new buffer if true.
bool isrBufNeeded = true;

// overrun count
uint16_t isrOver = 0;

// Ensure no timer events are missed.
volatile bool timerError = false;
volatile bool timerFlag = false;
