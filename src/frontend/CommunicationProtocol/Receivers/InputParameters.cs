using CommunicationProtocol.Senders;

namespace CommunicationProtocol.Receivers
{
    public class InputParameters : CSVReader<Parameter>
    {
        public InputParameters(string path) : base(path) {}

        protected override Parameter ParseRow(string[] values)
        {
            return new Parameter(values[headerMap["Name"]], values[headerMap["Value"]]);
        }

        public string GetValue(string name)
        {
            foreach (Parameter parameter in this)
            {
                if (parameter.Name == name)
                {
                    return parameter.Value;
                }
            }
            return null;
        }
    }
}