using System.Diagnostics;
using System.IO;
using UnityEngine;
using UnityEngine.UI;
using TMPro;
using UnityEngine.SceneManagement;

public class InputFields : MonoBehaviour
{

    // Variables
    private double primaryWeight = 0.0;
    private double primaryRampGeometry = 0.0;
    private double primarySpringRate = 0.0;
    private double primarySpringPretension = 0.0;
    private double secondaryHelixGeometry = 0.0;
    private double secondarySpringRate = 0.0;
    private double secondarySpringPretension = 0.0;
    private double vehicleWeight = 0.0;
    private double driverWeight = 0.0;
    private double traction = 0.0;
    private double angleOfIncline = 0.0;

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
        simulateButton.onClick.AddListener(LoadNextScene);
        primaryWeightInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref primaryWeight, ref primaryWeightInput, ref primaryWeightError));
        primaryRampGeometryInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref primaryRampGeometry, ref primaryRampGeometryInput, ref primaryRampGeometryError));
        primarySpringRateInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref primarySpringRate, ref primarySpringRateInput, ref primarySpringRateError));
        primarySpringPretensionInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref primarySpringPretension, ref primarySpringPretensionInput, ref primarySpringPretensionError));
        secondaryHelixGeometryInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref secondaryHelixGeometry, ref secondaryHelixGeometryInput, ref secondaryHelixGeometryError));
        secondarySpringRateInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref secondarySpringRate, ref secondarySpringRateInput, ref secondarySpringRateError));
        secondarySpringPretensionInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref secondarySpringPretension, ref secondarySpringPretensionInput, ref secondarySpringPretensionError));
        vehicleWeightInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref vehicleWeight, ref vehicleWeightInput, ref vehicleWeightError));
        driverWeightInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref driverWeight, ref driverWeightInput, ref driverWeightError));
        tractionInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref traction, ref tractionInput, ref tractionError));
        angleOfInclineInput.onValueChanged.AddListener((string value) => UpdateInputField(value, ref angleOfIncline, ref angleOfInclineInput, ref angleOfInclineError));

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

    private void LoadNextScene() {
        int nextSceneIndex = SceneManager.GetActiveScene().buildIndex + 1;
        SceneManager.LoadScene(nextSceneIndex);
    }

}