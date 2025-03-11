using System.Collections.Generic;
using System.Diagnostics;

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
        public void Run(string scriptPath, List<Parameter> parameters)
        {

            // Create a new process to run the python script
            ProcessStartInfo python = new ProcessStartInfo
            {
                FileName = environmentPath,
                Arguments = scriptPath + GenerateArgumentString(parameters),
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };

            // Execute the process
            using (Process process = Process.Start(python))
            {
                string result = process.StandardOutput.ReadToEnd();
                string error = process.StandardError.ReadToEnd();
            }
        }
    }
}


