using System.Collections.Generic;
using System.IO;
using UnityEngine;
using System;
using UnityEngine.UI;
using TMPro;

public class CSVReader : MonoBehaviour
{
    private readonly string csvPath = Path.GetFullPath(Path.Combine(Application.dataPath, "../simulation_output.csv"));

    [SerializeField] private Button playButton;
    [SerializeField] private Button pauseButton;
    [SerializeField] private TMP_Text statusText;
    [SerializeField] private Transform carTransform;


    private List<DataPoint> dataPoints = new List<DataPoint>();
    private bool isPlaying = false;
    private int currentIndex = 0;
    private float startTime;

    private float screenLeftBound;
    private float screenRightBound;

    

    private void Start()
    {
        // Set screen boundaries based on camera viewport
        screenLeftBound = Camera.main.ViewportToWorldPoint(new Vector3(0, 0, carTransform.position.z)).x;
        screenRightBound = Camera.main.ViewportToWorldPoint(new Vector3(1, 0, carTransform.position.z)).x;

        playButton.onClick.AddListener(StartPlayback);
        pauseButton.onClick.AddListener(PausePlayback);

        LoadCSVData();
    }

    private class DataPoint
    {
        public float Time { get; }
        public float Position { get; }

        public DataPoint(float time, float position)
        {
            Time = time;
            Position = position;
        }
    }

    private void LoadCSVData()
    {
        using (StreamReader reader = new StreamReader(csvPath))
        {
            // Read the header line
            string headerLine = reader.ReadLine();
            if (headerLine == null) return;

            // Get the indices for the time and car_position columns
            string[] headers = headerLine.Split(',');
            int timeIndex = Array.IndexOf(headers, "time");
            int positionIndex = Array.IndexOf(headers, "car_position");

            if (timeIndex == -1 || positionIndex == -1) return;

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

        statusText.text = "Data Loaded. Ready to Play.";
    }

    private void StartPlayback()
    {
        if (dataPoints.Count == 0) return;
        isPlaying = true;
        //currentIndex = 0;
        startTime = Time.time;
        StartCoroutine(PlaybackCoroutine());
        statusText.text = "Playing...";
    }

    private void PausePlayback()
    {
        isPlaying = false;
        statusText.text = "Paused";
    }

    private System.Collections.IEnumerator PlaybackCoroutine()
    {
        while (isPlaying && currentIndex < dataPoints.Count - 1)
        {
            float elapsedTime = Time.time - startTime;
            
            // Move to the next data point if enough time has passed
            while (currentIndex < dataPoints.Count - 1 && elapsedTime >= dataPoints[currentIndex + 1].Time)
            {
                currentIndex++;
                if (currentIndex == dataPoints.Count - 2)
                {
                    statusText.text = "Playback Finished";
                }
            }

            // Interpolate the position based on time for smooth movement
            if (currentIndex < dataPoints.Count - 1)
            {
                float timeA = dataPoints[currentIndex].Time;
                float timeB = dataPoints[currentIndex + 1].Time;
                float posA = dataPoints[currentIndex].Position;
                float posB = dataPoints[currentIndex + 1].Position;

                float t = (elapsedTime - timeA) / (timeB - timeA);
                float interpolatedPosition = Mathf.Lerp(posA, posB, t);

                float mappedPositionX = Mathf.Lerp(screenLeftBound, screenRightBound, interpolatedPosition / 200f);

                // Update the car's position in 3D space
                carTransform.position = new Vector3(mappedPositionX, carTransform.position.y, carTransform.position.z);

                // Calculate velocity based on change in position
                float velocity = (posB - posA) / (timeB - timeA);

                // Rotate the car based on velocity
                carTransform.Rotate(Vector3.forward * velocity * 10f * Time.deltaTime);
            }
            yield return null;
        }
        isPlaying = false;
    }

}
