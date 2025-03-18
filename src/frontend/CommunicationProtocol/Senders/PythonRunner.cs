using System.Collections.Generic;
using System.Diagnostics;
using System.Threading.Tasks;

namespace CommunicationProtocol.Senders
{
    public class Parameter
    {
        public string Name;
        public string Value;

        public Parameter(string name, string value)
        {
            Name = name;
            Value = value;
        }

        public string GenerateArgumentString()
        {
            return $" --{Name} {Value}";
        }
    }

    public class PythonRunner
    {
        // Path to the python environment
        private string environmentPath;


        // Constructor to find the python environment
        public PythonRunner(string environmentPath)
        {
            this.environmentPath = environmentPath;
        }

        private string GenerateArgumentString(List<Parameter> parameters)
        {
            string argumentString = "";
            foreach (Parameter parameter in parameters)
            {
                argumentString += parameter.GenerateArgumentString();
            }
            return argumentString;
        }

        // Main function to run the python script
        public Task RunAsync(string scriptPath, List<Parameter> parameters, bool debug = false)
        {
            return Task.Run(() =>
            {
                ProcessStartInfo startInfo = new ProcessStartInfo
                {
                    FileName = environmentPath,
                    Arguments = scriptPath + GenerateArgumentString(parameters),
                    UseShellExecute = debug,
                    CreateNoWindow = !debug
                };

                using (Process process = new Process())
                {
                    process.StartInfo = startInfo;
                    process.Start();
                    process.WaitForExit();
                }
            });
        }
    }
}


