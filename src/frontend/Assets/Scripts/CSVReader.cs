using System.Collections.Generic;
using System.IO;
using UnityEngine;
using System;
using System.Linq;

public class DataPoint
{
    public float Time { get; }
    public float CarPosition { get; }
    public float CarVelocity { get; }
    public float EngineRPM { get; }
    public float PrimaryAngle { get; }
    public float SecondaryAngle { get; }
    public float ShiftDistance { get; }

    public DataPoint(float time, float engineAngularVelocity, float engineAngularPosition, float carVelocity, float carPosition, float shiftDistance)
    {
        Time = time;
        CarPosition = carPosition;
        PrimaryAngle = RadiansToDegrees(engineAngularPosition);
        SecondaryAngle = RadiansToDegrees(CarPositionToSecondaryAngle(carPosition));
        ShiftDistance = shiftDistance;
        CarVelocity = MetersPerSecondToKmPerHour(carVelocity);
        EngineRPM = RadPerSecondToRPM(engineAngularVelocity);
    }

    private float RadiansToDegrees(float radians)
    {
        return radians * 180.0f / Mathf.PI;
    }

    private float CarPositionToSecondaryAngle(float position)
    {
        return position * (2.0f * 7.556f) / (22.0f * 0.0254f);
    }

    private float RadPerSecondToRPM(float radPerSecond)
    {
        return radPerSecond * 60 / (2 * Mathf.PI);
    }

    private float MetersPerSecondToKmPerHour(float metersPerSecond)
    {
        return metersPerSecond * 3.6f;
    }
}

public class CSVReader
{
    private readonly string csvPath = Path.GetFullPath(Path.Combine(Application.dataPath, "../simulation_output.csv"));

    private readonly string[] headers = new string[] { "time", "engine_angular_velocity", "engine_angular_position", "car_velocity", "car_position", "shift_distance" };

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

            Dictionary<string, int> headerIndices = new Dictionary<string, int>();
            string[] fileHeaders = headerLine.Split(',');

            foreach (string header in headers) 
            {
                headerIndices[header] = Array.IndexOf(fileHeaders, header);
            }

            if (headerIndices.ContainsValue(-1)) {
                throw new InvalidDataException("CSV file is missing required headers");
            }

            // Read each line, parsing time and position
            while (!reader.EndOfStream)
            {
                string line = reader.ReadLine();
                if (line == null) continue;

                string[] values = line.Split(',');


                if (values.Length > headerIndices.Values.Max())
                {
                    float time = float.Parse(values[headerIndices["time"]]);
                    float engineAngularVelocity = float.Parse(values[headerIndices["engine_angular_velocity"]]);
                    float engineAngularPosition = float.Parse(values[headerIndices["engine_angular_position"]]);
                    float carVelocity = float.Parse(values[headerIndices["car_velocity"]]);
                    float carPosition = float.Parse(values[headerIndices["car_position"]]);
                    float shiftDistance = float.Parse(values[headerIndices["shift_distance"]]);

                    dataPoints.Add(new DataPoint(time, engineAngularVelocity, engineAngularPosition, carVelocity, carPosition, shiftDistance));

                }
            }
        }
        return dataPoints;
    }
}