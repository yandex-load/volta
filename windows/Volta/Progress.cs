using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace vc
{
    static class Progress
    {
        static public int GetWaitTime(DateTime portOpenedOn, int minutesAmount, int maxAmount, int valueAmount)
        {
            int waitTime = (int)(new TimeSpan(0, minutesAmount, 0)).TotalMilliseconds / maxAmount;
            int undoneAmount = maxAmount - valueAmount;
            if ((undoneAmount > 0) && (undoneAmount < maxAmount))
            {
                TimeSpan spentTime = DateTime.Now.Subtract(portOpenedOn);
                TimeSpan leftTime = (new TimeSpan(0, minutesAmount, 0)).Subtract(spentTime);
                waitTime = (int)leftTime.TotalMilliseconds / undoneAmount;
                if (waitTime < 0) waitTime = 0;
            }
            return waitTime;
        }
        static public int GetPercent(int amount, int done)
        {
            return (int)(done * 100 / amount);
        }
        static public string GetTime(DateTime startedOn)
        {
            return DateTime.Now.Subtract(startedOn).ToString("mm\\:ss");
        }
        static public string GetStatus(string value, int count, int amount, DateTime startedOn)
        {
            return string.Format("{0}% - {1} / {2} ({3}): {4}                 ", GetPercent(amount, count), count, amount, GetTime(startedOn), value);
        }
    }
}
