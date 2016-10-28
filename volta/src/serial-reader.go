package main

import (
    "log"

    "bufio"
    "fmt"
    "github.com/tarm/serial"
    "time"
    "flag"
)

func main() {

    device := flag.String("device", "/dev/cu.wchusbserial1410",
        "USB device file")
    skip := flag.Int("skip", 500,
        "number of samples to skip (workaround to avoid dirty buffer)")
    nsamples := flag.Int("samples", 60 * 500, "number of samples to acquire")
    flag.Parse()
    c := &serial.Config{
        Name: *device,
        Baud: 115200,
    }
    s, err := serial.OpenPort(c)
    if err != nil {
        log.Fatal(err)
    }

    { // flush input buffer (dirty hack)
        buf := make([]byte, 256)
        n, err := s.Read(buf)
        for n == 256 {
            if err != nil {
                log.Fatal(err)
            }
            n, err = s.Read(buf)
        }
    }
    scanner := bufio.NewScanner(s)
    for i := 0; scanner.Scan() && i < *skip + *nsamples; i++ {
        if i < *skip {
            continue
        }
        fmt.Printf("%.6f %s\n", float64(time.Now().UnixNano())/1e9, scanner.Text())
    }
    if err := scanner.Err(); err != nil {
        log.Println("Error reading data:", err)
    }
}

