using System.Diagnostics;
using System.IO;
using UnityEngine;

// Struct defining the parameters of the python script
public struct Parameters
{
    // Parameter variables
    public double FlyweightMass;
    public double PrimaryRampGeometry;
    public double PrimarySpringRate;
    public double PrimarySpringPretension;
    public double SecondaryHelixGeometry;
    public double SecondaryTorsionSpringRate;
    public double SecondaryCompressionSpringRate;
    public double SecondarySpringPretension;
    public double VehicleWeight;
    public double DriverWeight;
    public double Traction;
    public double AngleOfIncline;

    // Generates the argument string using the struct fields
    public string GenerateArgumentString()
    {
        var fields = GetType().GetFields();
        string arguments = "";

        foreach (var field in fields)
        {
            string name = ConvertPascalToSnake(field.Name);
            arguments += " --" + name + " " + field.GetValue(this);
        }

        return arguments;
    }

    // Convert a pascal case string to snake case
    private string ConvertPascalToSnake(string name)
    {
        if (string.IsNullOrEmpty(name)) return name;

        return System.Text.RegularExpressions.Regex.Replace(
            name,
            "(?<!^)([A-Z])",
            "_$1"
        ).ToLower();
    }
    
}

public class PythonRunner
{
    // Paths to python environment and script
    private readonly string relativePythonPath = "../../../venv/Scripts/python.exe";
    
    // or for mac private readonly string relativePythonPath = "../../../venv/bin/python";
    private readonly string relativeScriptPath = "../../main.py";

    // Main function to run the python script
    public void RunPython(Parameters parameters)
    {   
        // Resolve the path to the python environment and main file of the python script
        string pythonPath = Path.GetFullPath(Path.Combine(Application.dataPath, relativePythonPath));
        string scriptPath = Path.GetFullPath(Path.Combine(Application.dataPath, relativeScriptPath));

        // Check if the python environment and the main file of the python script exist
        if (!File.Exists(pythonPath))
        {
            UnityEngine.Debug.LogError("Python environment not found at: " + pythonPath);
            return;
        }

        if (!File.Exists(scriptPath))
        {
            UnityEngine.Debug.LogError("Python script not found at: " + scriptPath);
            return;
        }

        // Create a new process to run the python script
        ProcessStartInfo python = new ProcessStartInfo {
            FileName = pythonPath,
            Arguments = scriptPath + parameters.GenerateArgumentString(),
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

            if (!string.IsNullOrEmpty(result))
            {
                UnityEngine.Debug.Log(result);
            }

            if (!string.IsNullOrEmpty(error))
            {
                UnityEngine.Debug.LogError(error);
            }
        }
    }
}