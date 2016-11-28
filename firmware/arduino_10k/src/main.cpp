#include <Arduino.h>

const char welcome[] = "\nVOLTAHELLO\n{\"sps\":10000}\nDATASTART\n";

uint16_t sensorValue = 0;
char buff[50];

#define BAUD 230400
#define TIMER_PRELOAD 65536-F_CPU/64/10000

#define cbi(sfr, bit) (_SFR_BYTE(sfr) &= ~_BV(bit))
#define sbi(sfr, bit) (_SFR_BYTE(sfr) |= _BV(bit))

#include <util/setbaud.h>

void uart_init(void) {
        UBRR0H = UBRRH_VALUE;
        UBRR0L = UBRRL_VALUE;

#if USE_2X
        UCSR0A |= _BV(U2X0);
#else
        UCSR0A &= ~(_BV(U2X0));
#endif

        UCSR0C = _BV(UCSZ01) | _BV(UCSZ00); /* 8-bit data */
        UCSR0B = _BV(RXEN0) | _BV(TXEN0); /* Enable RX and TX */
}

void inline uart_putchar(char c) {
        loop_until_bit_is_set(UCSR0A, UDRE0); /* Wait until data register empty. */
        UDR0 = c;
}

void inline uart_write_string(const char* buff) {
        for (int i = 0; buff[i]; i++) {
                uart_putchar(buff[i]);
        }
}

void inline uart_write_bytes(const char* buff, int len) {
        for (int i = 0; i<len; i++) {
                uart_putchar(buff[i]);
        }
}

void inline uart_write(unsigned long val) {
        uart_write_bytes((const char*)&val, sizeof(val));
}

void inline uart_write(uint16_t val) {
        uart_write_bytes((const char*)&val, sizeof(val));
}

void inline trigger_analog() {
        sbi(ADCSRA, ADSC);
}

uint16_t inline analog()
{
        while (bit_is_set(ADCSRA, ADSC)) ;
        uint16_t value = ADCW;
        return value;
}

void setup() {
        pinMode(A0, INPUT);
        // set up the ADC input and ref
        ADMUX = 0x40;
        // set prescale to 16
        sbi(ADCSRA,ADPS2);
        cbi(ADCSRA,ADPS1);
        cbi(ADCSRA,ADPS0);

        // set up UART and send welcome message
        uart_init();
        uart_write_string(welcome);

        // initialize timer1
        noInterrupts();
        TCCR1A = 0;
        TCCR1B = 0;

        TCNT1 = TIMER_PRELOAD;

        // 64 prescaler
        sbi(TCCR1B, CS10);
        sbi(TCCR1B, CS11);
        sbi(TIMSK1, TOIE1); // enable timer overflow interrupt
        interrupts();
}

ISR(TIMER1_OVF_vect) {
        TCNT1 = TIMER_PRELOAD;
        sensorValue = analog();
        trigger_analog();
        uart_write(sensorValue);
}

void loop() {}
