/*

Gather ADC data over wifi/udp

Connect to WiFi, then send commands over udp.

To subscribe, send udp packet with 'SUBS' command:
echo -n "SUBS" | nc -w1 -4u 192.168.4.1 2390

Listen for data on UDP/2390:
nc -ul 2390 > test.tsv

To stop, send 'STOP':
echo -n "STOP" | nc -w1 -4u 192.168.4.1 2390

Some debug info is in serial console:
picocom /dev/tty.SLAB_USBtoUART -b 9600
*/

#include <Wire.h>

#include "ADS1115.h"
#include "I2Cdev.h"

#include <ESP8266WiFi.h>
#include <WiFiClient.h>
#include <WiFiUdp.h>

/* Set these to your desired credentials. */
const char *ssid = "ESPap_1";
const char *password = "thereisnospoon";
const float multiplier = 0.125F;
const unsigned int localPort = 2390;
const unsigned int remotePort = 2390;
const unsigned int batchSize = 32;
unsigned long startTime = 0;
char packetBuffer[255];
char replyBuffer[32];
char delim[] = "\t";
char lineend[] = "\n";

const short cmdChars = 4;
char cmdSubscribe[] = "SUBS";
char cmdStop[] = "STOP";

ADS1115 ads(ADS1115_DEFAULT_ADDRESS);
const int alertReadyPin = D5;

WiFiUDP Udp;
IPAddress remoteIP;

void setup(void) {
    Wire.begin(D4, D3);
    Serial.begin(9600);
    Serial.println("Hello!");

    Serial.println("Testing device connections...");
    Serial.println(ads.testConnection() ? "ADS1115 connection successful" : "ADS1115 connection failed");

    ads.initialize();
    Serial.println("Getting reading from AIN0");
    ads.setGain(ADS1115_PGA_4P096);
    ads.setRate(ADS1115_RATE_860);
    ads.setMultiplexer(ADS1115_MUX_P0_NG);
    pinMode(alertReadyPin,INPUT_PULLUP);
    ads.setConversionReadyPinMode();
    ads.setMode(ADS1115_MODE_CONTINUOUS);
    Serial.println("ADC accuracy: 1 bit = 0.125mA");

    Serial.print("Configuring access point...");
    WiFi.softAP(ssid, password);

    IPAddress myIP = WiFi.softAPIP();
    Serial.print("AP IP address: ");
    Serial.println(myIP);

    Udp.begin(localPort);
}

void pollAlertReadyPin() {
  for (uint32_t i = 0; i<100000; i++)
    if (!digitalRead(alertReadyPin)) return;
   Serial.println("Failed to wait for AlertReadyPin, it's stuck high!");
}

void loop(void) {
     // if there's data available, read a packet
    int packetSize = Udp.parsePacket();
    if (packetSize) {
        Serial.print("Received packet of size ");
        Serial.println(packetSize);
        Serial.print("From ");
        Serial.print(Udp.remoteIP());
        Serial.print(", port ");
        Serial.println(Udp.remotePort());

        // read the packet into packetBufffer
        int len = Udp.read(packetBuffer, 255);
        packetBuffer[len] = 0;
        Serial.println("Contents:");
        Serial.println(packetBuffer);

        if (strncmp(packetBuffer, cmdSubscribe, cmdChars) == 0) {
            remoteIP = Udp.remoteIP();
            Serial.print("Subscribe remote IP: ");
            Serial.println(remoteIP);
            Udp.beginPacket(Udp.remoteIP(), Udp.remotePort());
            Udp.write("OK subscribed");
            Udp.write(lineend);
            Udp.endPacket();
            startTime = micros();
        } else if (strncmp(packetBuffer, cmdStop, cmdChars) == 0) {
            remoteIP = IPAddress();
            Serial.print("Unsubscribe");
            Udp.beginPacket(Udp.remoteIP(), Udp.remotePort());
            Udp.write("OK unsubscribed");
            Udp.write(lineend);
            Udp.endPacket();
        }
    }
    if (remoteIP) {
        Udp.beginPacket(remoteIP, remotePort);
        for (unsigned int i = 0; i < batchSize; i++) {
            pollAlertReadyPin();
            float current = ads.getMilliVolts(true);
            unsigned long time = micros() - startTime;
            Udp.write(ultoa(time, replyBuffer, 10));
            Udp.write(delim);
            Udp.write(dtostrf(current, 0, 2, replyBuffer));
            Udp.write(lineend);
        }
        Udp.write(lineend);
        Udp.endPacket();
    }
}
