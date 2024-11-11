using System.Diagnostics;
using System.IO;
using UnityEngine;
using UnityEngine.UI;
using TMPro;

public class PythonScriptRunner : MonoBehaviour
{
    // Serialize input parameters as private to make them visible in the Unity Editor
    [SerializeField] private double inclineAngle = 0.0;

    // Serialize reference objects
    [SerializeField] private Button runButton;
    [SerializeField] private TMP_InputField inclineAngleInput;

    private readonly string relativePythonPath = "../../../.venv/Scripts/python.exe";
    private readonly string relativeScriptPath = "../../main.py";

    private void Start()
    {
        // Add a listener to the run button
        runButton.onClick.AddListener(RunPython);

        // Add listeners for parameter inputs
        inclineAngleInput.onValueChanged.AddListener(UpdateInclineAngle);

    }

    private void UpdateInclineAngle(string value)
    {
        // Try to parse the input value to a double
        if (double.TryParse(value, out double angle))
        {
            inclineAngle = angle;
        } else {
            UnityEngine.Debug.LogError("Invalid input for incline angle: " + value);
        }
    }

    public void RunPython()
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

        // Create a string with all of the arguments
        string arguments = " --incline_angle " + inclineAngle;

        // Create a new process to run the python script
        ProcessStartInfo python = new ProcessStartInfo {
            FileName = pythonPath,
            Arguments = scriptPath + arguments,
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