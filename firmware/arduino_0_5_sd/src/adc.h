#ifndef adc_h
#define adc_h

#include "header.h"

// ADC configuration for each pin.
extern uint8_t adcmux[PIN_COUNT];
extern uint8_t adcsra[PIN_COUNT];
extern uint8_t adcsrb[PIN_COUNT];
extern uint8_t adcindex;

void adcInit(metadata_t* meta);
void adcStart();
void adcStop();

#endif // adc_h
