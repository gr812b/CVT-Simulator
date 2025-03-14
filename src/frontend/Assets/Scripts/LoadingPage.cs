using UnityEngine;
using CommunicationProtocol.Receivers;
using CommunicationProtocol.Senders;
using UnityEngine.SceneManagement;
using System.Linq;

public class LoadingPage : MonoBehaviour
{
    // PythonRunner to run the Python script and the InputParameters to match the input fields
    private PythonRunner pythonRunner = new PythonRunner(PathConstants.PYTHON_ENVIRONMENT_PATH);
    private InputParameters inputParameters = new InputParameters(PathConstants.INPUT_PARAMETERS_PATH);

    [SerializeField] private LoadingBar loadingBar;
    private PercentValue percentValue;
    private float currentPercent = 0;

    // Start is called once before the first execution of Update after the MonoBehaviour is created
    private void Start()
    {
        loadingBar.SetPercentage(currentPercent);

        // Run the Python script with the input parameters
        pythonRunner.Run(PathConstants.PYTHON_SCRIPT_PATH, inputParameters);
    }

    // Update is called once per frame
    private void Update() => UpdatePercent();

    private void UpdatePercent()
    {
        percentValue = new PercentValue(PathConstants.PERCENT_VALUE_PATH);

        // Get last value of percent from the array
        float percent = percentValue.Last();

        if (percent >= 1){
            NextScene();
        } else if (percent > currentPercent){
            currentPercent = percent;
            loadingBar.SetPercentage(currentPercent);
        }
    }

    private void NextScene()
    {
        int nextSceneIndex = SceneManager.GetActiveScene().buildIndex + 1;
        SceneManager.LoadScene(nextSceneIndex);
    }
}
