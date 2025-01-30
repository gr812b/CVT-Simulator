using System.Collections.Generic;
using System.IO;
using UnityEngine;
using System;
using UnityEngine.UI;
using TMPro;
using UnityEngine.SceneManagement;

// Interface encapsulating a component that displays playback data
public interface IPlaybackView
{
    public void Display(DataPoint dataPoint);
}

public class PlayBack : MonoBehaviour
{
    CSVReader csvReader = new CSVReader();
    private List<DataPoint> dataPoints;

    [SerializeField] private Button playButton;
    [SerializeField] private Button pauseButton;
    [SerializeField] private Button restartButton;
    [SerializeField] private Button nextSceneButton;
    [SerializeField] private TMP_Text statusText;
    [SerializeField] private IPlaybackView[] playbackViews;

    private bool isPlaying = false;
    private int currentIndex = 0;
    private float startTime;

    

    private void Start()
    {
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
                // Updates views to the current index and then moves to the next index
                UpdateViews();
                currentIndex++;
            }

            yield return null;
        }
        
        // Finishes playback and updates status text accordingly
        statusText.text = "Playback Finished";
        isPlaying = false;
    }

    // Updates all playback views with the current data point
    private void UpdateViews()
    {
        foreach (IPlaybackView view in playbackViews)
        {
            view.Display(dataPoints[currentIndex]);
        }
    }

    // Returns to the previous scene
    private void backButton()
        {
            int nextSceneIndex = SceneManager.GetActiveScene().buildIndex - 1;
            SceneManager.LoadScene(nextSceneIndex);
        }

}


