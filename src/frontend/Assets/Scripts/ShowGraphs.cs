using CommunicationProtocol.Receivers;
using CommunicationProtocol.Senders;
using UnityEngine;
using UnityEngine.UI;

class GraphButton : MonoBehaviour
{
    [SerializeField] private Button graphButton;

    private PythonRunner pythonRunner = new PythonRunner(PathConstants.PYTHON_ENVIRONMENT_PATH);

    private void Start()
    {
        graphButton.onClick.AddListener(ShowGraphs);
    }

    public void ShowGraphs()
    {
        InputParameters inputParameters = new InputParameters(PathConstants.INPUT_PARAMETERS_PATH);
        pythonRunner.RunAsync(PathConstants.GRAPH_SCRIPT_PATH, inputParameters);
    }
}