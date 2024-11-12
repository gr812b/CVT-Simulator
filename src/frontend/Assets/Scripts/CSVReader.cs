using System.IO;
using UnityEngine;
using System;
using UnityEngine.UI;
using TMPro;

public class CSVReader : MonoBehaviour
{
    private readonly string csvPath = Path.GetFullPath(Path.Combine(Application.dataPath, "../simulation_output.csv"));

    [SerializeField] private string columnName;
    [SerializeField] private Button readButton;
    [SerializeField] private TMP_Text outputText;

    private void Start()
    {
        readButton.onClick.AddListener(ReadColumn);
    }

    public void ReadColumn()
    {
        string output = ""; // Store the output text to display

        // Open the file with StreamReader
        using (StreamReader reader = new StreamReader(csvPath))
        {
            // Read the first line (header) to get the column names
            string headerLine = reader.ReadLine();
            if (headerLine == null) return;

            // Split the header into individual columns
            string[] headers = headerLine.Split(',');

            // Find the index of the specified column
            int columnIndex = Array.IndexOf(headers, columnName);
            if (columnIndex == -1) return; // Column not found

            // Read the rest of the lines
            while (!reader.EndOfStream)
            {
                string line = reader.ReadLine();
                if (line == null) continue;

                // Split the line by commas (assuming it's a comma-separated CSV)
                string[] values = line.Split(',');

                // Ensure there are enough columns in the line
                if (values.Length > columnIndex)
                {
                    // Parse the time and value columns as double (index 0 and the target column)
                    if (double.TryParse(values[0], out double time) && double.TryParse(values[columnIndex], out double value))
                    {
                        // Add the result to the output text
                        output += $"Time: {time}, Value: {value}\n";
                    }
                }
            }

            // Display the output text
            outputText.text = output;
        }
    }
}
