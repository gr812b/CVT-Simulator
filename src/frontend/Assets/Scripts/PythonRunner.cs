using System.Diagnostics;
using System.IO;
using UnityEngine;

public class PythonScriptRunner : MonoBehaviour
{
    public void RunPythonMain()
    {   
        // Resolve the path to the python environment and main file of the python script
        string pythonPath = Path.GetFullPath(Path.Combine(Application.dataPath, "../../../.venv/Scripts/python.exe"));
        string scriptPath = Path.GetFullPath(Path.Combine(Application.dataPath, "../../main.py"));

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
            Arguments = scriptPath,
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