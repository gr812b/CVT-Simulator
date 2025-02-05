using System.Collections.Generic;
using System.IO;
using UnityEngine;
using System;

public class DataPoint
{
    public float Time { get; }
    public float Position { get; }
    public float PrimaryAngle { get; }
    public float SecondaryAngle { get; }
    public float ShiftDistance { get; }
    public float Velocity { get; }
    public float AngularVelocity { get; }

    public DataPoint(float time, float position, float primaryAngle, float secondaryAngle, float shiftDistance, float velocity, float angularVelocity)
    {
        Time = time;
        Position = position;
        PrimaryAngle = primaryAngle;
        SecondaryAngle = secondaryAngle;
        ShiftDistance = shiftDistance;
        Velocity = velocity;
        AngularVelocity = angularVelocity;
    }
}

public class CSVReader
{

    private readonly string csvPath = Path.GetFullPath(Path.Combine(Application.dataPath, "../simulation_output.csv"));

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
            int velocityIndex = Array.IndexOf(headers, "car_velocity");
            int positionIndex = Array.IndexOf(headers, "car_position");
            int angularVelocityIndex = Array.IndexOf(headers, "engine_angular_velocity");

            if (timeIndex == -1 || positionIndex == -1 || velocityIndex == -1 || angularVelocityIndex == -1) {
                throw new InvalidDataException("CSV file does not contain required columns");
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
                        float.TryParse(values[positionIndex], out float position) && 
                        float.TryParse(values[velocityIndex], out float velocity) && 
                        float.TryParse(values[angularVelocityIndex], out float angular_velocity))
                    {
                        dataPoints.Add(new DataPoint(time, position, 0, 0, 0, velocity, angular_velocity));
                    }
                }
            }
        }
        return dataPoints;
    }

    private float RadiansToDegrees(float radians)
    {
        return radians * 180.0f / Mathf.PI;
    }

    private float CarPositionToSecondaryAngle(float position)
    {
        return position * (22.0f * 0.0254f) / (2.0f * 7.556f);
    }
}