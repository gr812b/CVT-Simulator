using System.Collections.Generic;
using System.IO;
using UnityEngine;
using System;
using UnityEngine.UI;
using TMPro;
using UnityEngine.SceneManagement;

public class PlayBack : MonoBehaviour
{
    CSVReader csvReader = new CSVReader();
    private List<CSVReader.DataPoint> dataPoints;

    [SerializeField] private Button playButton;
    [SerializeField] private Button pauseButton;
    [SerializeField] private Button restartButton;
    [SerializeField] private Button nextSceneButton;
    [SerializeField] private TMP_Text statusText;
    [SerializeField] private Transform carTransform;
    [SerializeField] private Transform carSpinTransform;

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
        restartButton.onClick.AddListener(RestartPlayback);
        nextSceneButton.onClick.AddListener(backButton);

        dataPoints = csvReader.LoadCSVData();
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

    private void RestartPlayback()
    {
        isPlaying = false;
        statusText.text = "Data Loaded. Ready to Play.";
        carTransform.position = new Vector3(screenLeftBound, carTransform.position.y, carTransform.position.z);
        currentIndex = 0;
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
                carSpinTransform.Rotate(Vector3.forward * velocity * 10f * Time.deltaTime);
            }
            yield return null;
        }
        isPlaying = false;
    }

    private void backButton()
        {
            int nextSceneIndex = SceneManager.GetActiveScene().buildIndex - 1;
            SceneManager.LoadScene(nextSceneIndex);
        }

}


