using System.Diagnostics;
using System.IO;
using UnityEngine;
using UnityEngine.UI;
using TMPro;
using UnityEngine.SceneManagement;

public class InputFields : MonoBehaviour
{
    // Runner for the python script
    private PythonRunner pythonRunner = new PythonRunner();

    // Parameters struct to store the input fields
    private Parameters parameters = new Parameters
    {
        PrimaryWeight = 0.0,
        PrimaryRampGeometry = 0.0,
        PrimarySpringRate = 0.0,
        PrimarySpringPretension = 0.0,
        SecondaryHelixGeometry = 0.0,
        SecondarySpringRate = 0.0,
        SecondarySpringPretension = 0.0,
        VehicleWeight = 0.0,
        DriverWeight = 0.0,
        Traction = 0.0,
        AngleOfIncline = 0.0
    };

    // Buttons
    [SerializeField] private Button simulateButton;

    // Input fields
    [SerializeField] private TMP_InputField primaryWeightInput;
    [SerializeField] private TMP_InputField primaryRampGeometryInput;
    [SerializeField] private TMP_InputField primarySpringRateInput;
    [SerializeField] private TMP_InputField primarySpringPretensionInput;
    [SerializeField] private TMP_InputField secondaryHelixGeometryInput;
    [SerializeField] private TMP_InputField secondarySpringRateInput;
    [SerializeField] private TMP_InputField secondarySpringPretensionInput;
    [SerializeField] private TMP_InputField vehicleWeightInput;
    [SerializeField] private TMP_InputField driverWeightInput;
    [SerializeField] private TMP_InputField tractionInput;
    [SerializeField] private TMP_InputField angleOfInclineInput;

    // Text Fields
    [SerializeField] private TMP_Text primaryWeightError;
    [SerializeField] private TMP_Text primaryRampGeometryError;
    [SerializeField] private TMP_Text primarySpringRateError;
    [SerializeField] private TMP_Text primarySpringPretensionError;
    [SerializeField] private TMP_Text secondaryHelixGeometryError;
    [SerializeField] private TMP_Text secondarySpringRateError;
    [SerializeField] private TMP_Text secondarySpringPretensionError;
    [SerializeField] private TMP_Text vehicleWeightError;
    [SerializeField] private TMP_Text driverWeightError;
    [SerializeField] private TMP_Text tractionError;
    [SerializeField] private TMP_Text angleOfInclineError;


    private void Start() {
        simulateButton.onClick.AddListener(StartSimulation);
        primaryWeightInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref parameters.PrimaryWeight, ref primaryWeightInput, ref primaryWeightError));
        primaryRampGeometryInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref parameters.PrimaryRampGeometry, ref primaryRampGeometryInput, ref primaryRampGeometryError));
        primarySpringRateInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref parameters.PrimarySpringRate, ref primarySpringRateInput, ref primarySpringRateError));
        primarySpringPretensionInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref parameters.PrimarySpringPretension, ref primarySpringPretensionInput, ref primarySpringPretensionError));
        secondaryHelixGeometryInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref parameters.SecondaryHelixGeometry, ref secondaryHelixGeometryInput, ref secondaryHelixGeometryError));
        secondarySpringRateInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref parameters.SecondarySpringRate, ref secondarySpringRateInput, ref secondarySpringRateError));
        secondarySpringPretensionInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref parameters.SecondarySpringPretension, ref secondarySpringPretensionInput, ref secondarySpringPretensionError));
        vehicleWeightInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref parameters.VehicleWeight, ref vehicleWeightInput, ref vehicleWeightError));
        driverWeightInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref parameters.DriverWeight, ref driverWeightInput, ref driverWeightError));
        tractionInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref parameters.Traction, ref tractionInput, ref tractionError));
        angleOfInclineInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref parameters.AngleOfIncline, ref angleOfInclineInput, ref angleOfInclineError));

    }

    private void UpdateInputField(string value, ref double field, ref TMP_InputField inputField, ref TMP_Text errorText) {
        if (double.TryParse(value, out double val)) {
            field = val;
            inputField.image.color = Color.white;
            errorText.text = "";
        } else {
            UnityEngine.Debug.LogError("Invalid input for field: " + value);
            inputField.image.color = Color.red;
            errorText.text = "Invalid input, enter a number";
        }
    }

    private void StartSimulation() {
        // Run the python script with the input parameters
        pythonRunner.RunPython(parameters);

        // Go the the results scene
        int nextSceneIndex = SceneManager.GetActiveScene().buildIndex + 1;
        SceneManager.LoadScene(nextSceneIndex);
    }

}