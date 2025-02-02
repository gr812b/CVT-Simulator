using System.Collections.Generic;
using System.IO;
using UnityEngine;
using System;
using UnityEngine.UI;
using TMPro;
using UnityEngine.SceneManagement;

public class CSVReader
{

    private readonly string csvPath = Path.GetFullPath(Path.Combine(Application.dataPath, "../simulation_output.csv"));

    public class DataPoint
    {
        public float Time { get; }
        public float Position { get; }

        public DataPoint(float time, float position)
        {
            Time = time;
            Position = position;
        }
    }

    public List<DataPoint> LoadCSVData()
    {
        List<DataPoint> dataPoints = new List<DataPoint>();
    
        using (StreamReader reader = new StreamReader(csvPath))
        {
            // Read the header line
            string headerLine = reader.ReadLine();
            if (headerLine == null) {
                throw new InvalidDataException("CSV file is empty");
            }

            // Get the indices for the time and car_position columns
            string[] headers = headerLine.Split(',');
            int timeIndex = Array.IndexOf(headers, "time");
            int positionIndex = Array.IndexOf(headers, "car_position");

            if (timeIndex == -1 || positionIndex == -1) {
                throw new InvalidDataException("CSV file does not contain time and car_position columns");
            }

            // Read each line, parsing time and position
            while (!reader.EndOfStream)
            {
                string line = reader.ReadLine();
                if (line == null) continue;

                string[] values = line.Split(',');

                if (values.Length > Math.Max(timeIndex, positionIndex))
                {
                    if (float.TryParse(values[timeIndex], out float time) &&
                        float.TryParse(values[positionIndex], out float position))
                    {
                        dataPoints.Add(new DataPoint(time, position));
                    }
                }
            }
        }
        return dataPoints;
    }
}