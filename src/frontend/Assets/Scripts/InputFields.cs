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
        FlyweightMass = 0.0,
        PrimaryRampGeometry = 0.0,
        PrimarySpringRate = 0.0,
        PrimarySpringPretension = 0.0,
        SecondaryHelixGeometry = 0.0,
        SecondaryTorsionSpringRate = 0.0,
        SecondaryCompressionSpringRate = 0.0,
        SecondarySpringPretension = 0.0,
        VehicleWeight = 0.0,
        DriverWeight = 0.0,
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

    // Default Values
    private double defaultFlyweightMass = 0.8;
    private double defaultPrimaryRampGeometry = 0.0;
    private double defaultPrimarySpringRate = 500;
    private double defaultPrimarySpringPretension = 0.2;
    private double defaultSecondaryHelixGeometry = 0.0;
    private double defaultSecondaryTorsionSpringRate = 5;
    private double defaultSecondaryCompressionSpringRate = 100;
    private double defaultSecondarySpringPretension = 15;
    private double defaultVehicleWeight = 226.8;
    private double defaultDriverWeight = 77.1107;
    private double defaultTraction = 0.0;
    private double defaultAngleOfIncline = 0.0;


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
        inputDefaultValues(ref flyweightMassInput, ref flyweightMassError, defaultFlyweightMass);
        inputDefaultValues(ref primaryRampGeometryInput, ref primaryRampGeometryError, defaultPrimaryRampGeometry);
        inputDefaultValues(ref primarySpringRateInput, ref primarySpringRateError, defaultPrimarySpringRate);
        inputDefaultValues(ref primarySpringPretensionInput, ref primarySpringPretensionError, defaultPrimarySpringPretension);
        inputDefaultValues(ref secondaryHelixGeometryInput, ref secondaryHelixGeometryError, defaultSecondaryHelixGeometry);
        inputDefaultValues(ref secondaryTorsionSpringRateInput, ref secondaryTorsionSpringRateError, defaultSecondaryTorsionSpringRate);
        inputDefaultValues(ref secondaryCompressionSpringRateInput, ref secondaryCompressionSpringRateError, defaultSecondaryCompressionSpringRate);
        inputDefaultValues(ref secondarySpringPretensionInput, ref secondarySpringPretensionError, defaultSecondarySpringPretension);
        inputDefaultValues(ref vehicleWeightInput, ref vehicleWeightError, defaultVehicleWeight);
        inputDefaultValues(ref driverWeightInput, ref driverWeightError, defaultDriverWeight);
        inputDefaultValues(ref tractionInput, ref tractionError, defaultTraction);
        inputDefaultValues(ref angleOfInclineInput, ref angleOfInclineError, defaultAngleOfIncline);
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