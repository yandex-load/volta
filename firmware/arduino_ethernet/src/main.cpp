/*
 * UIPEthernet UdpServer example.
 *
 * UIPEthernet is a TCP/IP stack that can be used with a enc28j60 based
 * Ethernet-shield.
 *
 * UIPEthernet uses the fine uIP stack by Adam Dunkels <adam@sics.se>
 *
 *      -----------------
 *
 * This UdpServer example sets up a udp-server at 192.168.0.6 on port 5000.
 * send packet via upd to test
 *
 * Copyright (C) 2013 by Norbert Truchsess (norbert.truchsess@t-online.de)
 */

#include <UIPEthernet.h>


// Define various ADC prescaler
const unsigned char PS_16 = (1 << ADPS2);
const unsigned char PS_32 = (1 << ADPS2) | (1 << ADPS0);
const unsigned char PS_64 = (1 << ADPS2) | (1 << ADPS1);
const unsigned char PS_128 = (1 << ADPS2) | (1 << ADPS1) | (1 << ADPS0);

EthernetUDP Udp;
const int sensorPin = A0; 
const unsigned int localPort = 2390;
const unsigned int remotePort = 2390;
const unsigned int batchSize = 128;
unsigned long startTime = 0;
char packetBuffer[255];
char replyBuffer[32];
char delim[] = "\t";
char lineend[] = "\n";

const short cmdChars = 4;
char cmdSubscribe[] = "SUBS";
char cmdStop[] = "STOP";

IPAddress remoteIP;

void setup() {

    pinMode(sensorPin, INPUT);

    // set up the ADC
    ADCSRA &= ~PS_128;  // remove bits set by Arduino library

    // you can choose a prescaler from above.
    // PS_16, PS_32, PS_64 or PS_128
    ADCSRA |= PS_64;    // set our own prescaler to 64 
    Serial.begin(9600);

    uint8_t mac[6] = {0x00,0x01,0x02,0x03,0x04,0x05};

    Ethernet.begin(mac,IPAddress(192,168,1,78));

    int success = Udp.begin(localPort);

    Serial.print("initialize: ");
    Serial.println(success ? "success" : "failed");

}

void loop() {
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
        Udp.stop();
        Udp.begin(localPort);
    }
    if (remoteIP) {
        Udp.beginPacket(remoteIP, remotePort);
        for (unsigned int i = 0; i < batchSize; i++) {
            unsigned long time = micros() - startTime;
            int current = analogRead(sensorPin);
            unsigned long time_m = micros() - startTime;
            Udp.write(ultoa(time, replyBuffer, 10), strlen(replyBuffer));
            Udp.write(delim, 1);
            Udp.write(itoa(current, replyBuffer, 10), strlen(replyBuffer));
            unsigned long time_s = micros() - startTime;
            Udp.write(delim, 1);
            Udp.write(ultoa(time_m - time, replyBuffer, 10), strlen(replyBuffer));
            Udp.write(delim, 1);
            Udp.write(ultoa(time_s - time_m, replyBuffer, 10), strlen(replyBuffer));
            Udp.write(lineend);
            Serial.print(time_m - time);
            Serial.print(delim);
            Serial.println(time_s - time_m);
        }
        Udp.write(lineend);
        Udp.endPacket();
        Udp.stop();
        Udp.begin(localPort);
    }
}
