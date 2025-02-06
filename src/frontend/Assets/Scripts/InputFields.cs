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
    private bool canSimulate = false;

    // Parameters struct to store the input fields
    public Parameters parameters = new Parameters
    {
        FlyweightMass = 0.8,
        PrimaryRampGeometry = 0.0,
        PrimarySpringRate = 500.0,
        PrimarySpringPretension = 0.2,
        SecondaryHelixGeometry = 0.0,
        SecondaryTorsionSpringRate = 5.0,
        SecondaryCompressionSpringRate = 100.0,
        SecondarySpringPretension = 15.0,
        VehicleWeight = 226.8,
        DriverWeight = 77.107,
        Traction = 0.0,
        AngleOfIncline = 0.0
    };

    // Buttons
    [SerializeField] private Button simulateButton;
    [SerializeField] private Button defaultButton;

    // Input fields
    [SerializeField] private TMP_InputField flyweightMassInput;
    [SerializeField] private TMP_InputField primaryRampGeometryInput;
    [SerializeField] private TMP_InputField primarySpringRateInput;
    [SerializeField] private TMP_InputField primarySpringPretensionInput;
    [SerializeField] private TMP_InputField secondaryHelixGeometryInput;
    [SerializeField] private TMP_InputField secondaryTorsionSpringRateInput;
    [SerializeField] private TMP_InputField secondaryCompressionSpringRateInput;
    [SerializeField] private TMP_InputField secondarySpringPretensionInput;
    [SerializeField] private TMP_InputField vehicleWeightInput;
    [SerializeField] private TMP_InputField driverWeightInput;
    [SerializeField] private TMP_InputField tractionInput;
    [SerializeField] private TMP_InputField angleOfInclineInput;

    // Text Fields
    [SerializeField] private TMP_Text flyweightMassError;
    [SerializeField] private TMP_Text primaryRampGeometryError;
    [SerializeField] private TMP_Text primarySpringRateError;
    [SerializeField] private TMP_Text primarySpringPretensionError;
    [SerializeField] private TMP_Text secondaryHelixGeometryError;
    [SerializeField] private TMP_Text secondaryTorsionSpringRateError;
    [SerializeField] private TMP_Text secondaryCompressionSpringRateError;
    [SerializeField] private TMP_Text secondarySpringPretensionError;
    [SerializeField] private TMP_Text vehicleWeightError;
    [SerializeField] private TMP_Text driverWeightError;
    [SerializeField] private TMP_Text tractionError;
    [SerializeField] private TMP_Text angleOfInclineError;

    private void Start() {
        simulateButton.onClick.AddListener(StartSimulation);
        SetDefaultValues();
        flyweightMassInput.onValueChanged.AddListener((string value) => validInput(value, ref parameters.FlyweightMass, ref flyweightMassInput, ref flyweightMassError));
        primaryRampGeometryInput.onValueChanged.AddListener((string value) => validInput(value, ref parameters.PrimaryRampGeometry, ref primaryRampGeometryInput, ref primaryRampGeometryError));
        primarySpringRateInput.onValueChanged.AddListener((string value) => validInput(value, ref parameters.PrimarySpringRate, ref primarySpringRateInput, ref primarySpringRateError));
        primarySpringPretensionInput.onValueChanged.AddListener((string value) => validInput(value, ref parameters.PrimarySpringPretension, ref primarySpringPretensionInput, ref primarySpringPretensionError));
        secondaryHelixGeometryInput.onValueChanged.AddListener((string value) => validInput(value, ref parameters.SecondaryHelixGeometry, ref secondaryHelixGeometryInput, ref secondaryHelixGeometryError));
        secondaryTorsionSpringRateInput.onValueChanged.AddListener((string value) => validInput(value, ref parameters.SecondaryTorsionSpringRate, ref secondaryTorsionSpringRateInput, ref secondaryTorsionSpringRateError));
        secondaryCompressionSpringRateInput.onValueChanged.AddListener((string value) => validInput(value, ref parameters.SecondaryCompressionSpringRate, ref secondaryCompressionSpringRateInput, ref secondaryCompressionSpringRateError));
        secondarySpringPretensionInput.onValueChanged.AddListener((string value) => validInput(value, ref parameters.SecondarySpringPretension, ref secondarySpringPretensionInput, ref secondarySpringPretensionError));
        vehicleWeightInput.onValueChanged.AddListener((string value) => validInput(value, ref parameters.VehicleWeight, ref vehicleWeightInput, ref vehicleWeightError));
        driverWeightInput.onValueChanged.AddListener((string value) => validInput(value, ref parameters.DriverWeight, ref driverWeightInput, ref driverWeightError));
        tractionInput.onValueChanged.AddListener((string value) => validInput(value, ref parameters.Traction, ref tractionInput, ref tractionError));
        angleOfInclineInput.onValueChanged.AddListener((string value) => validInput(value, ref parameters.AngleOfIncline, ref angleOfInclineInput, ref angleOfInclineError));
    }

    private void validInput(string value, ref double field, ref TMP_InputField inputField, ref TMP_Text errorText) {
        if (double.TryParse(value, out double val) && val >= 0) {
            field = val;
            inputField.image.color = Color.white;
            errorText.text = "";
        } else {
            UnityEngine.Debug.LogError("Invalid input for field: " + value);
            inputField.image.color = Color.red;
            errorText.text = "Invalid input, enter a number";
        }
    }

    private void verifyFieldNotEmpty(ref TMP_InputField inputField, ref TMP_Text errorText) {
        if (inputField.text == "") {
            inputField.image.color = Color.red;
            errorText.text = "Required field";
            canSimulate = false;
        } else {
            inputField.image.color = Color.white;
            errorText.text = "";
            canSimulate = true;
        }
    }

    private void inputDefaultValues(ref TMP_InputField inputField, ref TMP_Text errorText, double value) {
        inputField.text = value.ToString();
        errorText.text = "";
    }

    private void SetDefaultValues() {
        inputDefaultValues(ref flyweightMassInput, ref flyweightMassError, parameters.FlyweightMass);
        inputDefaultValues(ref primaryRampGeometryInput, ref primaryRampGeometryError, parameters.PrimaryRampGeometry);
        inputDefaultValues(ref primarySpringRateInput, ref primarySpringRateError, parameters.PrimarySpringRate);
        inputDefaultValues(ref primarySpringPretensionInput, ref primarySpringPretensionError, parameters.PrimarySpringPretension);
        inputDefaultValues(ref secondaryHelixGeometryInput, ref secondaryHelixGeometryError, parameters.SecondaryHelixGeometry);
        inputDefaultValues(ref secondaryTorsionSpringRateInput, ref secondaryTorsionSpringRateError, parameters.SecondaryTorsionSpringRate);
        inputDefaultValues(ref secondaryCompressionSpringRateInput, ref secondaryCompressionSpringRateError, parameters.SecondaryCompressionSpringRate);
        inputDefaultValues(ref secondarySpringPretensionInput, ref secondarySpringPretensionError, parameters.SecondarySpringPretension);
        inputDefaultValues(ref vehicleWeightInput, ref vehicleWeightError, parameters.VehicleWeight);
        inputDefaultValues(ref driverWeightInput, ref driverWeightError, parameters.DriverWeight);
        inputDefaultValues(ref tractionInput, ref tractionError, parameters.Traction);
        inputDefaultValues(ref angleOfInclineInput, ref angleOfInclineError, parameters.AngleOfIncline);
    }
    private void checkFields() {
        verifyFieldNotEmpty(ref flyweightMassInput, ref flyweightMassError);
        verifyFieldNotEmpty(ref primaryRampGeometryInput, ref primaryRampGeometryError);
        verifyFieldNotEmpty(ref primarySpringRateInput, ref primarySpringRateError);
        verifyFieldNotEmpty(ref primarySpringPretensionInput, ref primarySpringPretensionError);
        verifyFieldNotEmpty(ref secondaryHelixGeometryInput, ref secondaryHelixGeometryError);
        verifyFieldNotEmpty(ref secondaryTorsionSpringRateInput, ref secondaryTorsionSpringRateError);
        verifyFieldNotEmpty(ref secondaryCompressionSpringRateInput, ref secondaryCompressionSpringRateError);
        verifyFieldNotEmpty(ref secondarySpringPretensionInput, ref secondarySpringPretensionError);
        verifyFieldNotEmpty(ref vehicleWeightInput, ref vehicleWeightError);
        verifyFieldNotEmpty(ref driverWeightInput, ref driverWeightError);
        verifyFieldNotEmpty(ref tractionInput, ref tractionError);
        verifyFieldNotEmpty(ref angleOfInclineInput, ref angleOfInclineError);
    }

    private void StartSimulation() {
        // Run the python script with the input parameters
        checkFields();
        if (!canSimulate) {
            return;
        }
        pythonRunner.RunPython(parameters);

        // Go the the results scene
        DontDestroyOnLoad(this.gameObject);
        int nextSceneIndex = SceneManager.GetActiveScene().buildIndex + 1;
        SceneManager.LoadScene(nextSceneIndex);
    }

}