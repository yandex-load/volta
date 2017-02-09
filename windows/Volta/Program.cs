using System;
using System.Collections.Generic;
using System.IO.Ports;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace vc
{
    class Program
    {
        static string fileName;
        static void Main(string[] args)
        {
            if (args.Length == 0)
            {
                Console.WriteLine("Отсутствует обязательный параметр: <имя файла>");
                Console.WriteLine(">vc.exe NavigatorTest1.log");
                Console.WriteLine("Нажмите ENTER...");
                Console.Read();
            }
            else
            {
                string[] ports = SerialPort.GetPortNames();
                while (ports.Length == 0)
                {
                    Console.WriteLine("Порт не обнаружен.");
                    Console.WriteLine("Выполните следующие действия:");
                    string[] intro = Instruction.GetIntro();
                    for (int i = 0; i < intro.Length; i++)
                    {
                        Console.WriteLine("{0}. {1}", i + 1, intro[i]);
                    }
                    Thread.Sleep(2000);
                    Console.Clear();
                    ports = SerialPort.GetPortNames();
                }
                Console.WriteLine("Порт: {0}", ports[0]);

                fileName = args[0];
                Start(ports[0]);
                while ((serialPort != null) && (serialPort.IsOpen))
                {
                    Thread.Sleep(Progress.GetWaitTime(serialPortOpenedOn, measurements.Duration, measurements.Amount, valueAmount));
                }
            }
        }

        static SerialPort serialPort;
        static int valueAmount = 0;
        static Measurements measurements = new Measurements(5, 30000);
        static DateTime serialPortOpenedOn;
        static void serialPortDataReceived(object sender, SerialDataReceivedEventArgs e)
        {
            Thread.Sleep(Progress.GetWaitTime(serialPortOpenedOn, measurements.Duration, measurements.Amount, valueAmount));
            try
            {
                if (serialPort.IsOpen)
                {
                    string data = serialPort.ReadLine();
                    valueAmount++;
                    measurements.Values[valueAmount - 1] = new Measurement();
                    measurements.Values[valueAmount - 1].Time = DateTime.Now;
                    measurements.Values[valueAmount - 1].Value = double.Parse(data.Replace(".", ","));
                    Console.SetCursorPosition(25, 1);
                    Console.Write(Progress.GetStatus(data, valueAmount, measurements.Amount, serialPortOpenedOn));
                }
            }
            catch (Exception exception)
            {
                Console.WriteLine("Exception: {0}", exception.Message);
            }
            if (valueAmount >= measurements.Amount)
            {
                Stop();
            }
        }
        static void Start(string port)
        {
            serialPort = new SerialPort(port, 115200, Parity.None, 8, StopBits.One);
            serialPort.Handshake = Handshake.None;
            serialPort.DtrEnable = true;
            serialPort.ReadTimeout = 1000;
            serialPort.Open();
            serialPort.DiscardInBuffer();
            serialPortOpenedOn = DateTime.Now;
            serialPort.DataReceived += new SerialDataReceivedEventHandler(serialPortDataReceived);
            Console.WriteLine("Замер энергопотребления:");
        }
        static void Stop()
        {
            measurements.Save(fileName);
            if ((serialPort != null) && (serialPort.IsOpen))
            {
                serialPort.Close();
            }
        }
    }
}