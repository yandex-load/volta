int sensorPin = A0;    // select the input pin for the potentiometer
int sensorValue = 0;  // variable to store the value coming from the sensor

int relayPin = 2;
char relayOpened='1';

void setup() {
  pinMode(sensorPin, INPUT);
  pinMode(relayPin, OUTPUT); 
  digitalWrite(relayPin, HIGH);
  Serial.begin(115200);
  
  // initialize timer1 
  noInterrupts();           // disable all interrupts
  TCCR1A = 0;
  TCCR1B = 0;
  TCNT1 = 65411;            // preload timer 65536-16MHz/256/500Hz
  TCCR1B |= (1 << CS12);    // 256 prescaler 
  TIMSK1 |= (1 << TOIE1);   // enable timer overflow interrupt
  interrupts();             // enable all interrupts
}

// interrupt service routine that wraps a user defined function 
// supplied by attachInterrupt
ISR(TIMER1_OVF_vect) {
  TCNT1 = 65411;            // preload timer
  sensorValue = analogRead(sensorPin);
  float mamps = (sensorValue * 5000.0 )/ 1024.0;
  Serial.print(mamps);
  Serial.print("\n");
}

void loop() {
  if (Serial.available()) {
    relayOpened = Serial.read();
    if (relayOpened=='1') {
      digitalWrite(relayPin, HIGH);
    }
    else if(relayOpened=='0') {
      digitalWrite(relayPin, LOW);
    }
  }
}
