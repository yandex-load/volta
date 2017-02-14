#include "adc.h"

//==============================================================================
extern SdFat sd;
extern SdBaseFile binFile;
extern Bounce debouncer;
extern char binName[13];

typedef block16_t block_t;

extern block_t* emptyQueue[QUEUE_DIM];
extern uint8_t emptyHead;
extern uint8_t emptyTail;

extern block_t* fullQueue[QUEUE_DIM];
extern volatile uint8_t fullHead;  // volatile ensures non-interrupt code sees changes.
extern uint8_t fullTail;

// Pointer to current buffer.
extern block_t* isrBuf;

// Need new buffer if true.
extern bool isrBufNeeded;

// overrun count
extern uint16_t isrOver;

// Ensure no timer events are missed.
extern volatile bool timerError;
extern volatile bool timerFlag;
