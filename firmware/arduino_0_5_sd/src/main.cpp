/**
 * This program logs data from the Arduino ADC to a binary file.
 * Data is written to the file using a SD multiple block write command.
 * Based on SdFat AnalogBinLogger example.
 */
#include "header.h"

// queueNext assumes QUEUE_DIM is a power of two
inline uint8_t queueNext(uint8_t ht) {
  return (ht + 1) & (QUEUE_DIM -1);
}
//==============================================================================
// Interrupt Service Routines

//------------------------------------------------------------------------------
// ADC done interrupt.
ISR(ADC_vect) {
  // Read ADC data.
#if RECORD_EIGHT_BITS
  uint8_t d = ADCH;
#else  // RECORD_EIGHT_BITS
  // This will access ADCL first.
  uint16_t d = ADC;
#endif  // RECORD_EIGHT_BITS

  if (isrBufNeeded && emptyHead == emptyTail) {
    // no buffers - count overrun
    if (isrOver < 0XFFFF) {
      isrOver++;
    }

    // Avoid missed timer error.
    timerFlag = false;
    return;
  }
  // Start ADC
  if (PIN_COUNT > 1) {
    ADMUX = adcmux[adcindex];
    ADCSRB = adcsrb[adcindex];
    ADCSRA = adcsra[adcindex];
    if (adcindex == 0) {
      timerFlag = false;
    }
    adcindex =  adcindex < (PIN_COUNT - 1) ? adcindex + 1 : 0;
  } else {
    timerFlag = false;
  }
  // Check for buffer needed.
  if (isrBufNeeded) {
    // Remove buffer from empty queue.
    isrBuf = emptyQueue[emptyTail];
    emptyTail = queueNext(emptyTail);
    isrBuf->count = 0;
    isrBuf->overrun = isrOver;
    isrBufNeeded = false;
  }
  // Store ADC data.
  isrBuf->data[isrBuf->count++] = d;

  // Check for buffer full.
  if (isrBuf->count >= PIN_COUNT*SAMPLES_PER_BLOCK) {
    // Put buffer isrIn full queue.
    uint8_t tmp = fullHead;  // Avoid extra fetch of volatile fullHead.
    fullQueue[tmp] = (block_t*)isrBuf;
    fullHead = queueNext(tmp);

    // Set buffer needed and clear overruns.
    isrBufNeeded = true;
    isrOver = 0;
  }
}
//------------------------------------------------------------------------------
// timer1 interrupt to clear OCF1B
ISR(TIMER1_COMPB_vect) {
  // Make sure ADC ISR responded to timer event.
  if (timerFlag) {
    timerError = true;
  }
  timerFlag = true;
}

#if ADPS0 != 0 || ADPS1 != 1 || ADPS2 != 2
#error unexpected ADC prescaler bits
#endif

//------------------------------------------------------------------------------
// log data
void logData() {
  uint32_t bgnBlock, endBlock;

  // Allocate extra buffer space.
  block_t block[BUFFER_BLOCK_COUNT];

  Serial.println();

  // Initialize ADC and timer1.
  adcInit((metadata_t*) &block[0]);

  // initialize file system.
  Serial.println("Initialize file system.");
  if (!sd.begin(SD_CS_PIN, SPI_FULL_SPEED)) {
    sd.initErrorPrint();
    fatalBlink();
  }

  // Find unused file name.
  if (BASE_NAME_SIZE > 6) {
    error("FILE_BASE_NAME too long");
  }
  while (sd.exists(binName)) {
    if (binName[BASE_NAME_SIZE + 1] != '9') {
      binName[BASE_NAME_SIZE + 1]++;
    } else {
      binName[BASE_NAME_SIZE + 1] = '0';
      if (binName[BASE_NAME_SIZE] == '9') {
        error("Can't create file name");
      }
      binName[BASE_NAME_SIZE]++;
    }
  }
  // Create new file.
  Serial.print(F("Creating new file: "));
  Serial.println(binName);
  binFile.close();
  if (!binFile.createContiguous(sd.vwd(),
                                binName, 512 * FILE_BLOCK_COUNT)) {
    error("createContiguous failed");
  }
  // Get the address of the file on the SD.
  if (!binFile.contiguousRange(&bgnBlock, &endBlock)) {
    error("contiguousRange failed");
  }
  // Use SdFat's internal buffer.
  uint8_t* cache = (uint8_t*)sd.vol()->cacheClear();
  if (cache == 0) {
    error("cacheClear failed");
  }

  // Flash erase all data in the file.
  Serial.println(F("Erasing all data"));
  uint32_t bgnErase = bgnBlock;
  uint32_t endErase;
  while (bgnErase < endBlock) {
    endErase = bgnErase + ERASE_SIZE;
    if (endErase > endBlock) {
      endErase = endBlock;
    }
    if (!sd.card()->erase(bgnErase, endErase)) {
      error("erase failed");
    }
    bgnErase = endErase + 1;
  }
  // Start a multiple block write.
  if (!sd.card()->writeStart(bgnBlock, FILE_BLOCK_COUNT)) {
    error("writeBegin failed");
  }
  // Write metadata.
  if (!sd.card()->writeData((uint8_t*)&block[0])) {
    error("Write metadata failed");
  }
  // Initialize queues.
  emptyHead = emptyTail = 0;
  fullHead = fullTail = 0;

  // Use SdFat buffer for one block.
  emptyQueue[emptyHead] = (block_t*)cache;
  emptyHead = queueNext(emptyHead);

  // Put rest of buffers in the empty queue.
  for (uint8_t i = 0; i < BUFFER_BLOCK_COUNT; i++) {
    emptyQueue[emptyHead] = &block[i];
    emptyHead = queueNext(emptyHead);
  }
  // Give SD time to prepare for big write.
  delay(1000);
  Serial.println(F("Logging - type any character to stop"));
  // Wait for Serial Idle.
  Serial.flush();
  delay(10);
  uint32_t bn = 1;
  uint32_t t0 = millis();
  uint32_t t1 = t0;
  uint32_t overruns = 0;
  uint32_t count = 0;
  uint32_t maxLatency = 0;

  // Start logging interrupts.
  if(WRITE_LED_PIN > 0) {
    digitalWrite(WRITE_LED_PIN, HIGH);
  }

  adcStart();
  while (1) {
    if (fullHead != fullTail) {
      // Get address of block to write.
      block_t* pBlock = fullQueue[fullTail];

      // Write block to SD.
      uint32_t usec = micros();
      if (!sd.card()->writeData((uint8_t*)pBlock->data)) {
        error("write data failed");
      }
      usec = micros() - usec;
      t1 = millis();
      if (usec > maxLatency) {
        maxLatency = usec;
      }
      count += pBlock->count;

      // Add overruns and possibly light LED.
      if (pBlock->overrun) {
        overruns += pBlock->overrun;
        if (ERROR_LED_PIN >= 0) {
          digitalWrite(ERROR_LED_PIN, HIGH);
        }
      }
      // Move block to empty queue.
      emptyQueue[emptyHead] = pBlock;
      emptyHead = queueNext(emptyHead);
      fullTail = queueNext(fullTail);
      bn++;
      if (bn == FILE_BLOCK_COUNT) {
        // File full so stop ISR calls.
        adcStop();
        break;
      }
    }
    if (timerError) {
      error("Missed timer event - rate too high");
    }
    // Update the Bounce instance :
    debouncer.update();

    // Get the updated value :
    int sw_value = debouncer.read();
    if (Serial.available() or sw_value == HIGH) {
      if(WRITE_LED_PIN > 0) {
        digitalWrite(WRITE_LED_PIN, LOW);
      }
      // Stop ISR calls.
      adcStop();
      if (isrBuf != 0 && isrBuf->count >= PIN_COUNT) {
        // Truncate to last complete sample.
        isrBuf->count = PIN_COUNT*(isrBuf->count/PIN_COUNT);
        // Put buffer in full queue.
        fullQueue[fullHead] = isrBuf;
        fullHead = queueNext(fullHead);
        isrBuf = 0;
      }
      if (fullHead == fullTail) {
        break;
      }
    }
  }
  if (!sd.card()->writeStop()) {
    error("writeStop failed");
  }
  // Truncate file if recording stopped early.
  if (bn != FILE_BLOCK_COUNT) {
    Serial.println(F("Truncating file"));
    if (!binFile.truncate(512L * bn)) {
      error("Can't truncate file");
    }
  }
  binFile.close();
  Serial.print(F("File dumped: "));
  Serial.println(binName);
  Serial.print(F("Max block write usec: "));
  Serial.println(maxLatency);
  Serial.print(F("Record time sec: "));
  Serial.println(0.001*(t1 - t0), 3);
  Serial.print(F("Sample count: "));
  Serial.println(count/PIN_COUNT);
  Serial.print(F("Samples/sec: "));
  Serial.println((1000.0/PIN_COUNT)*count/(t1-t0));
  Serial.print(F("Overruns: "));
  Serial.println(overruns);
  Serial.println(F("Done"));
}
//------------------------------------------------------------------------------
void setup(void) {
  // Setup the dump switch with an internal pull-up :
  pinMode(DUMP_SW_PIN,INPUT_PULLUP);

  // After setting up the button, setup the Bounce instance :
  debouncer.attach(DUMP_SW_PIN);
  debouncer.interval(5); // interval in ms
  if (ERROR_LED_PIN >= 0) {
    pinMode(ERROR_LED_PIN, OUTPUT);
  }
  if (WRITE_LED_PIN >= 0) {
    pinMode(WRITE_LED_PIN, OUTPUT);
  }
  Serial.begin(9600);

  // Read the first sample pin to init the ADC.
  analogRead(PIN_LIST[0]);

  Serial.print(F("FreeStack: "));
  Serial.println(FreeStack());

}
//------------------------------------------------------------------------------
void loop(void) {
  // discard any input
  while (Serial.read() >= 0) {}
  Serial.println();
  Serial.println(F("type:"));
  Serial.println(F("r - record ADC data"));

  int sw_value = HIGH;
  while(!Serial.available()) {
    // Update the Bounce instance :
    debouncer.update();

    // Get the updated value :
    sw_value = debouncer.read();
    if(sw_value == LOW) break;
  }
  char c = tolower(Serial.read());
  if(sw_value == LOW) c = 'r';
  if (ERROR_LED_PIN >= 0) {
    digitalWrite(ERROR_LED_PIN, LOW);
  }
  // Read any extra Serial data.
  do {
    delay(10);
  } while (Serial.read() >= 0);

  if (c == 'r') {
    logData();
  } else {
    Serial.println(F("Invalid entry"));
  }
}
