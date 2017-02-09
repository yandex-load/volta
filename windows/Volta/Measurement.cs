using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace vc
{
    class Measurements
    {
        public Measurements(int measDurationMin, int measAmount)
        {
            duration = measDurationMin;
            amount = measAmount;
            values = new Measurement[amount];
        }

        private int duration;
        public int Duration
        {
            get
            {
                return duration;
            }
        }
        private int amount;
        public int Amount
        {
            get
            {
                return amount;
            }
        }
        private Measurement[] values;
        public Measurement[] Values
        {
            get
            {
                return values;
            }
            set
            {
                values = value;
            }
        }


        public static double DateTimeToUnixTimestamp(DateTime dateTime)
        {
            return (TimeZoneInfo.ConvertTimeToUtc(dateTime) -
                   new DateTime(1970, 1, 1, 0, 0, 0, 0, System.DateTimeKind.Utc)).TotalSeconds;
        }
        public static DateTime JavaTimeStampToDateTime(double javaTimeStamp)
        {
            // Java timestamp is millisecods past epoch
            System.DateTime dtDateTime = new DateTime(1970, 1, 1, 0, 0, 0, 0, System.DateTimeKind.Utc);
            dtDateTime = dtDateTime.AddSeconds(Math.Round(javaTimeStamp / 1000)).ToLocalTime();
            return dtDateTime;
        }
        public static string DoubleToUnixString(double dValue, int adjustment)
        {
            string value = dValue.ToString();
            if (value.IndexOf(",") < 0)
            {
                value += ",0";
            }
            string[] vSet = value.Split(',');
            while (vSet[1].Length < adjustment)
            {
                vSet[1] += "0";
            }
            return string.Format("{0}.{1}", vSet[0], vSet[1]);
        }

        public void Save(string fileName)
        {
            if (File.Exists(fileName))
            {
                File.Delete(fileName);
            }
            StreamWriter streamWriter = new StreamWriter(fileName, true, Encoding.Default);
            foreach (Measurement measurement in Values)
            {
                streamWriter.WriteLine("{0} {1}", DoubleToUnixString(DateTimeToUnixTimestamp(measurement.Time), 6), DoubleToUnixString(measurement.Value, 2));
            }
            streamWriter.Close();
            streamWriter.Dispose();
        }
    }
    class Measurement
    {
        public DateTime Time { get; set; }
        public double Value { get; set; }
    }
}
