using System.Diagnostics;
using System.IO;
using UnityEngine;
using UnityEngine.UI;
using TMPro;
using UnityEngine.SceneManagement;

public static class SimulationData
{
    public static Parameters parameters = new Parameters
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
}
public class InputFields : MonoBehaviour
{
    // Runner for the python script
    private PythonRunner pythonRunner = new PythonRunner();
    private bool canSimulate = false;

    public Parameters parameters;

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
        parameters = SimulationData.parameters;
        LoadStoredValues();
        LoadStoredValues(); // Load saved values when scene starts
        simulateButton.onClick.AddListener(StartSimulation);
        flyweightMassInput.onValueChanged.AddListener((value) => UpdateParameter(value, ref SimulationData.parameters.FlyweightMass, flyweightMassInput, flyweightMassError));
        primaryRampGeometryInput.onValueChanged.AddListener((value) => UpdateParameter(value, ref SimulationData.parameters.PrimaryRampGeometry, primaryRampGeometryInput, primaryRampGeometryError));
        primarySpringRateInput.onValueChanged.AddListener((value) => UpdateParameter(value, ref SimulationData.parameters.PrimarySpringRate, primarySpringRateInput, primarySpringRateError));
        primarySpringPretensionInput.onValueChanged.AddListener((value) => UpdateParameter(value, ref SimulationData.parameters.PrimarySpringPretension, primarySpringPretensionInput, primarySpringPretensionError));
        secondaryHelixGeometryInput.onValueChanged.AddListener((value) => UpdateParameter(value, ref SimulationData.parameters.SecondaryHelixGeometry, secondaryHelixGeometryInput, secondaryHelixGeometryError));
        secondaryTorsionSpringRateInput.onValueChanged.AddListener((value) => UpdateParameter(value, ref SimulationData.parameters.SecondaryTorsionSpringRate, secondaryTorsionSpringRateInput, secondaryTorsionSpringRateError));
        secondaryCompressionSpringRateInput.onValueChanged.AddListener((value) => UpdateParameter(value, ref SimulationData.parameters.SecondaryCompressionSpringRate, secondaryCompressionSpringRateInput, secondaryCompressionSpringRateError));
        secondarySpringPretensionInput.onValueChanged.AddListener((value) => UpdateParameter(value, ref SimulationData.parameters.SecondarySpringPretension, secondarySpringPretensionInput, secondarySpringPretensionError));
        vehicleWeightInput.onValueChanged.AddListener((value) => UpdateParameter(value, ref SimulationData.parameters.VehicleWeight, vehicleWeightInput, vehicleWeightError));
        driverWeightInput.onValueChanged.AddListener((value) => UpdateParameter(value, ref SimulationData.parameters.DriverWeight, driverWeightInput, driverWeightError));
        tractionInput.onValueChanged.AddListener((value) => UpdateParameter(value, ref SimulationData.parameters.Traction, tractionInput, tractionError));
        angleOfInclineInput.onValueChanged.AddListener((value) => UpdateParameter(value, ref SimulationData.parameters.AngleOfIncline, angleOfInclineInput, angleOfInclineError));
    }

    private void LoadStoredValues() {
        flyweightMassInput.text = SimulationData.parameters.FlyweightMass.ToString();
        primaryRampGeometryInput.text = SimulationData.parameters.PrimaryRampGeometry.ToString();
        primarySpringRateInput.text = SimulationData.parameters.PrimarySpringRate.ToString();
        primarySpringPretensionInput.text = SimulationData.parameters.PrimarySpringPretension.ToString();
        secondaryHelixGeometryInput.text = SimulationData.parameters.SecondaryHelixGeometry.ToString();
        secondaryTorsionSpringRateInput.text = SimulationData.parameters.SecondaryTorsionSpringRate.ToString();
        secondaryCompressionSpringRateInput.text = SimulationData.parameters.SecondaryCompressionSpringRate.ToString();
        secondarySpringPretensionInput.text = SimulationData.parameters.SecondarySpringPretension.ToString();
        vehicleWeightInput.text = SimulationData.parameters.VehicleWeight.ToString();
        driverWeightInput.text = SimulationData.parameters.DriverWeight.ToString();
        tractionInput.text = SimulationData.parameters.Traction.ToString();
        angleOfInclineInput.text = SimulationData.parameters.AngleOfIncline.ToString();
    }

    private void UpdateParameter(string value, ref double parameter, TMP_InputField inputField, TMP_Text errorText) {
    if (double.TryParse(value, out double val) && val >= 0) {
        parameter = val; // Store updated value in static class
        inputField.image.color = Color.white;
        errorText.text = "";
    } else {
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
        pythonRunner.RunPython(SimulationData.parameters);

        // Go the the results scene
        DontDestroyOnLoad(this.gameObject);
        int nextSceneIndex = SceneManager.GetActiveScene().buildIndex + 1;
        SceneManager.LoadScene(nextSceneIndex);
    }

    private void OnDestroy()
    {
        // Save changes before exiting the scene
        SimulationData.parameters = parameters;
    }

}