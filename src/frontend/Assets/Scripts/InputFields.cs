using System.Diagnostics;
using System.IO;
using UnityEngine;
using UnityEngine.UI;
using TMPro;
using UnityEngine.SceneManagement;
using System.Collections.Generic;

public static class SimulationData
{
    public static Parameters parameters = new Parameters
    {
        FlyweightMass = 0.6,
        PrimaryRampGeometry = 0.0,
        PrimarySpringRate = 500.0,
        PrimarySpringPretension = 0.2,
        SecondaryHelixGeometry = 0.0,
        SecondaryTorsionSpringRate = 100.0,
        SecondaryCompressionSpringRate = 100.0,
        SecondarySpringPretension = 15.0,
        VehicleWeight = 225.0,
        DriverWeight = 75.0,
        Traction = 100.0,
        AngleOfIncline = 0.0
    };
}

[System.Serializable]
public class ParameterFields
{
    public TMP_InputField inputField;
    public TMP_Text errorText;
    public string parameterName;
    public System.Action<double> setParameter;
}

public class InputFields : MonoBehaviour
{
    // Runner for the python script
    private PythonRunner pythonRunner = new PythonRunner();
    private bool canSimulate = false;

    public Parameters parameters;

    // Buttons
    [SerializeField] private Button simulateButton;

    // List of all parameter fields
    [SerializeField] private List<ParameterFields> parameterFields;

     private void Start()
    {
        LoadStoredValues();

        simulateButton.onClick.AddListener(StartSimulation);

        // Add listeners dynamically for all fields
        foreach (var field in parameterFields)
        {
            field.inputField.onValueChanged.AddListener(value => UpdateParameter(value, field));
        }
    }

    private void LoadStoredValues()
    {
        foreach (var field in parameterFields)
        {
            double value = GetParameterValue(field.parameterName);
            field.inputField.text = value.ToString();
        }
    }

    private double GetParameterValue(string name)
    {
        return name switch
        {
            "FlyweightMass" => SimulationData.parameters.FlyweightMass,
            "PrimaryRampGeometry" => SimulationData.parameters.PrimaryRampGeometry,
            "PrimarySpringRate" => SimulationData.parameters.PrimarySpringRate,
            "PrimarySpringPretension" => SimulationData.parameters.PrimarySpringPretension,
            "SecondaryHelixGeometry" => SimulationData.parameters.SecondaryHelixGeometry,
            "SecondaryTorsionSpringRate" => SimulationData.parameters.SecondaryTorsionSpringRate,
            "SecondaryCompressionSpringRate" => SimulationData.parameters.SecondaryCompressionSpringRate,
            "SecondarySpringPretension" => SimulationData.parameters.SecondarySpringPretension,
            "VehicleWeight" => SimulationData.parameters.VehicleWeight,
            "DriverWeight" => SimulationData.parameters.DriverWeight,
            "Traction" => SimulationData.parameters.Traction,
            "AngleOfIncline" => SimulationData.parameters.AngleOfIncline,
            _ => 0.0
        };
    }

    private void SetParameterValue(string name, double value)
    {
        switch (name)
        {
            case "FlyweightMass": SimulationData.parameters.FlyweightMass = value; break;
            case "PrimaryRampGeometry": SimulationData.parameters.PrimaryRampGeometry = value; break;
            case "PrimarySpringRate": SimulationData.parameters.PrimarySpringRate = value; break;
            case "PrimarySpringPretension": SimulationData.parameters.PrimarySpringPretension = value; break;
            case "SecondaryHelixGeometry": SimulationData.parameters.SecondaryHelixGeometry = value; break;
            case "SecondaryTorsionSpringRate": SimulationData.parameters.SecondaryTorsionSpringRate = value; break;
            case "SecondaryCompressionSpringRate": SimulationData.parameters.SecondaryCompressionSpringRate = value; break;
            case "SecondarySpringPretension": SimulationData.parameters.SecondarySpringPretension = value; break;
            case "VehicleWeight": SimulationData.parameters.VehicleWeight = value; break;
            case "DriverWeight": SimulationData.parameters.DriverWeight = value; break;
            case "Traction": SimulationData.parameters.Traction = value; break;
            case "AngleOfIncline": SimulationData.parameters.AngleOfIncline = value; break;
        }
    }

    private void UpdateParameter(string value, ParameterFields field)
    {
        if (double.TryParse(value, out double val) && val >= 0)
        {
            SetParameterValue(field.parameterName, val);
            field.inputField.image.color = Color.white;
            field.errorText.text = "";
        }
        else
        {
            field.inputField.image.color = Color.red;
            field.errorText.text = "Invalid input, enter a number";
        }
    }

    private void CheckFields()
    {
        canSimulate = true;
        foreach (var field in parameterFields)
        {
            if (string.IsNullOrWhiteSpace(field.inputField.text))
            {
                field.inputField.image.color = Color.red;
                field.errorText.text = "Required field";
                canSimulate = false;
            }
        }
    }
    
    private void StartSimulation() {
        // Run the python script with the input parameters
        CheckFields();
        if (!canSimulate) {
            return;
        }
        pythonRunner.RunPython(SimulationData.parameters);

        // Go the the results scene
        DontDestroyOnLoad(this.gameObject);
        int nextSceneIndex = SceneManager.GetActiveScene().buildIndex + 1;
        SceneManager.LoadScene(nextSceneIndex);
    }

    private void OnDestroy()
    {
        foreach (var field in parameterFields)
        {
            double value = double.TryParse(field.inputField.text, out double val) ? val : 0.0;
            SetParameterValue(field.parameterName, value);
        }
    }

}