using System;
using System.Collections.Generic;
using System.Text;

namespace CommunicationProtocol.Receivers
{
    public class PercentValue: CSVReader<float>
    {
        public PercentValue(string path) : base(path) { }

        protected override float ParseRow(string[] values)
        {
            return float.Parse(values[headerMap["Percent"]]);
        }
    }
}
