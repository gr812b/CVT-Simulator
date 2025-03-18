using System.IO;
using UnityEngine;
using UnityEngine.UI;
using SFB; 

public class DownloadCSV : MonoBehaviour
{
    private readonly string csvDataPath = PathConstants.SIMULATION_OUTPUT_PATH;
    private readonly string csvParamsPath = PathConstants.INPUT_PARAMETERS_PATH;

    [SerializeField] private Button downloadDataButton;
    [SerializeField] private Button downloadParamsButton;

    private void Start() {
        downloadDataButton.onClick.AddListener(() => DownloadCSVFile(csvDataPath, "simulation_output"));
        downloadParamsButton.onClick.AddListener(() => DownloadCSVFile(csvParamsPath, "input_parameters"));
    }

    private void DownloadCSVFile(string sourcePath, string defaultFileName) {
        string destinationPath = StandaloneFileBrowser.SaveFilePanel(
            "Save CSV File",        // Title of the dialog
            "",                    // Initial directory (empty defaults to user's Documents)
            defaultFileName,         // Default file name
            "csv"                   // Default file extension
        );

        if (!string.IsNullOrEmpty(destinationPath)) {
            File.Copy(sourcePath, destinationPath, true);
        }
    } 
}