using UnityEngine;
using UnityEngine.UI;
using TMPro;
using UnityEngine.SceneManagement;
using System.Collections.Generic;
using CommunicationProtocol.Senders;
using CommunicationProtocol.Receivers;
using System.Linq;
using System.IO;
using SFB;
using CommunicationProtocol.Senders;

// Class to make the input fields serializable
[System.Serializable]
public class ParameterField {
    public string parameterName;
    public TMP_InputField inputField;
    public TMP_Text errorText;

}

// Class to manage behaviour of the input fields
public class InputField
{
    private TMP_InputField inputField;
    private TMP_Text errorText;
    
    private bool IsNumber(string value) => double.TryParse(value, out double val) && val >= 0;
    private bool IsEmpty(string value) => string.IsNullOrWhiteSpace(value);
    public bool IsValid => IsNumber(inputField.text) && !IsEmpty(inputField.text);

    // Constructor to set the input field, error text and add a listener to the parameter
    public InputField(TMP_InputField inputField, TMP_Text errorText, Parameter parameter)
    {
        this.inputField = inputField;
        this.errorText = errorText;
        AddParameterListener(parameter);
    }

    // Sets the parameter to update when the input field changes
    private void AddParameterListener(Parameter parameter)
    {
        inputField.text = parameter.Value; // Set the text to the initial value
        inputField.onValueChanged.AddListener(value => UpdateParameterValue(value, parameter));
    }

    private void UpdateParameterValue(string value, Parameter parameter)
    {
        if (IsEmpty(value))
        {
            inputField.image.color = Color.red;
            errorText.text = "Required field";
        }
        else if (!IsNumber(value))
        {
            inputField.image.color = Color.red;
            errorText.text = "Invalid input, enter a number";
        }
        else
        {
            parameter.Value = value;
            inputField.image.color = Color.white;
            errorText.text = "";
        }
    }
}

public class UserInput : MonoBehaviour
{

    // Input store to save the input parameters
    private InputStore inputStore = new InputStore();
    public List<Parameter> parameters = DefaultParameters.parameters;
    
    // Input fields
    [SerializeField] List<ParameterField> parameterFields;
    private List<InputField> inputFields = new List<InputField>();

    // Buttons
    [SerializeField] private Button simulateButton;
    [SerializeField] private Button uploadButton;

    private PythonRunner runner = new PythonRunner(PathConstants.PYTHON_ENVIRONMENT_PATH);

    private void UpdateParameters()
    {
        if (File.Exists(PathConstants.INPUT_PARAMETERS_PATH))
        {
            parameters = new InputParameters(PathConstants.INPUT_PARAMETERS_PATH);
        }
        
        // Add parameter listeners to input fields
        foreach(ParameterField field in parameterFields)
        {
            Parameter parameter = parameters.Find(p => p.Name == field.parameterName);
            inputFields.Add(new InputField(field.inputField, field.errorText, parameter));
        }
    }

    private void Start()
    {
        simulateButton.onClick.AddListener(StartSimulation);
        uploadButton.onClick.AddListener(Upload);

        // Check if the input fields csv file exists and load the parameters if it does
        UpdateParameters();
    }

    private void Upload() 
    {
        //open file explorer and accept a csv then rename the csv to input_parameters.csv
        string[] paths = StandaloneFileBrowser.OpenFilePanel("Open CSV File", "", "csv", false);
        if (paths.Length > 0) {
            File.Copy(paths[0], Path.Combine(Application.dataPath, "../input_parameters.csv"), true);
        }

        UpdateParameters();
    }
    
    private void StartSimulation() {
        // Run the python script with the input parameters
        if (!inputFields.All(field => field.IsValid))
        {
            return;
        }

        inputStore.Store(PathConstants.INPUT_PARAMETERS_PATH, parameters);
        runner.Run(PathConstants.PYTHON_SCRIPT_PATH, parameters, true);

        // Go the the results scene
        int nextSceneIndex = SceneManager.GetActiveScene().buildIndex + 1;
        SceneManager.LoadScene(nextSceneIndex);
    }

    
}