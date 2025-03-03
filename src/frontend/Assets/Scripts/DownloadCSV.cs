using System.IO;
using UnityEngine;
using UnityEngine.UI;
using SFB; 

public class DownloadCSV : MonoBehaviour
{
    private readonly string csvPath = Path.Combine(Application.dataPath, "../simulation_output.csv");

    [SerializeField] private Button downloadButton;

    private void Start() {
        downloadButton.onClick.AddListener(Download);
    }

    private void Download() {
       
        string destinationPath = StandaloneFileBrowser.SaveFilePanel(
            "Save CSV File",        // Title of the dialog
            "",                    // Initial directory (empty defaults to user's Documents)
            "simulation_output",   // Default file name
            "csv"                  // Default file extension
        );


        if (!string.IsNullOrEmpty(destinationPath)) {
            File.Copy(csvPath, destinationPath, true);
            Debug.Log("Downloaded CSV file to: " + destinationPath);
        } else {
            Debug.Log("Save operation canceled.");
        }
    } 
}