#undef HID_ENABLED

// Arduino Due ADC->DMA->USB 1MSPS
// by stimmer
// from http://forum.arduino.cc/index.php?topic=137635.msg1136315#msg1136315
// Input: Analog in A0
// Output: Raw stream of uint16_t in range 0-4095 on Native USB Serial/ACM

// on linux, to stop the OS cooking your data: 
// stty -F /dev/ttyACM0 raw -iexten -echo -echoe -echok -echoctl -echoke -onlcr

const uint16_t nbuffers = 8; // should be power of 2!
const uint16_t bufmask = nbuffers - 1;
const uint16_t bufsize = 512;

volatile int bufn, obufn;
uint16_t buf[nbuffers][bufsize];

void ADC_Handler(){     // move DMA pointers to next buffer
  int f=ADC->ADC_ISR;
  if (f&(1<<27)){
   bufn=(bufn+1)&bufmask;
   ADC->ADC_RNPR=(uint32_t)buf[bufn];
   ADC->ADC_RNCR=bufsize;
  }
}

void setup(){
  SerialUSB.begin(0);
  while(!SerialUSB);
  pmc_enable_periph_clk(ID_ADC);
  adc_init(ADC, SystemCoreClock, 21UL * 1000000UL, ADC_STARTUP_FAST);
  adc_set_resolution(ADC, ADC_12_BITS);
  ADC->ADC_MR |=0x80; // free running

  ADC->ADC_CHER=0x80; 

  NVIC_EnableIRQ(ADC_IRQn);
  ADC->ADC_IDR=~(1<<27);
  ADC->ADC_IER=1<<27;
  ADC->ADC_RPR=(uint32_t)buf[0];   // DMA buffer
  ADC->ADC_RCR=bufsize;
  ADC->ADC_RNPR=(uint32_t)buf[1]; // next DMA buffer
  ADC->ADC_RNCR=bufsize;
  bufn=1;
  obufn=0;
  ADC->ADC_PTCR=1;
  ADC->ADC_CR=2;
}

void loop(){
  while((obufn + 1)%nbuffers==bufn); // wait for buffer to be full
  SerialUSB.write((uint8_t *)buf[obufn], bufsize*2);
  obufn=(obufn+1)&bufmask;    
}
