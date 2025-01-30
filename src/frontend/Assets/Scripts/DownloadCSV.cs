using System.Collections.Generic;
using System.IO;
using UnityEngine;
using System;
using UnityEngine.UI;
using TMPro;
using UnityEngine.SceneManagement;
using SFB; // Namespace for StandaloneFileBrowser

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

        // If the user selects a path (not cancel)
        if (!string.IsNullOrEmpty(destinationPath)) {
            // Copy the file to the selected location
            File.Copy(csvPath, destinationPath, true);
            Debug.Log("Downloaded CSV file to: " + destinationPath);
        } else {
            Debug.Log("Save operation canceled.");
        }
    } 
}