using UnityEngine;
using UnityEngine.UI;
using TMPro;
using UnityEngine.SceneManagement;
using System.IO;
using System.Collections;
using CommunicationProtocol.Receivers;


// Abstract class encapsulating a component that displays playback data
public abstract class PlaybackView : MonoBehaviour
{
    public abstract void Display(DataPoint dataPoint);
}

public class Playback : MonoBehaviour
{
    private SimulationResult simulationResult;

    [SerializeField] private Button playPauseButton;
    [SerializeField] private Button restartButton;
    [SerializeField] private Button nextSceneButton;
    [SerializeField] private Slider seekBar;  
    [SerializeField] private PlaybackView[] playbackViews;
    [SerializeField] private RawImage playImage;
    [SerializeField] private RawImage pauseImage;


    private bool isPlaying = false;
    private int currentIndex = 0;
    private float accumulatedTime = 0f;

    private void Start()
    {
        playPauseButton.onClick.AddListener(TogglePlayPause);
        restartButton.onClick.AddListener(RestartPlayback);
        nextSceneButton.onClick.AddListener(BackButton);
        seekBar.onValueChanged.AddListener(OnSeekBarChanged);

        // Get path to simulation result file and then read it
        simulationResult = new SimulationResult(PathConstants.SIMULATION_OUTPUT_PATH);
        seekBar.minValue = 0;
        seekBar.maxValue = simulationResult.Count - 1;
        seekBar.value = 0;
    }

    void TogglePlayPause()
    {
        if (simulationResult.Count == 0) return;

        isPlaying = !isPlaying;

        if (isPlaying)
        {
            playImage.gameObject.SetActive(false);
            pauseImage.gameObject.SetActive(true);
            StartCoroutine(PlaybackCoroutine());
        }
        else
        {
            playImage.gameObject.SetActive(true);
            pauseImage.gameObject.SetActive(false);
        }
    }

    private void RestartPlayback()
    {
        isPlaying = false;
        currentIndex = 0;
        accumulatedTime = 0f;
        playImage.gameObject.SetActive(true);
        pauseImage.gameObject.SetActive(false);
        seekBar.value = 0;
    }

    private IEnumerator PlaybackCoroutine()
    {
        while (isPlaying && currentIndex < simulationResult.Count - 1)
        {
            accumulatedTime += Time.deltaTime; // Increment elapsed time

            // Move to the next data point if enough time has passed
            while (currentIndex < simulationResult.Count - 1 && accumulatedTime >= simulationResult[currentIndex + 1].Time)
            {
                UpdateViews();
                currentIndex++;
                seekBar.value = currentIndex;
            }

            yield return null;
        }

        isPlaying = false;
    }

    private void UpdateViews()
    {
        foreach (PlaybackView view in playbackViews)
        {
            view.Display(simulationResult[currentIndex]);
        }
    }

    private void OnSeekBarChanged(float value)
    {
        currentIndex = Mathf.RoundToInt(value); // Convert float to int
        accumulatedTime = simulationResult[currentIndex].Time; // Sync time to new index
        UpdateViews();
    }

    private void BackButton()
    {
        int nextSceneIndex = SceneManager.GetActiveScene().buildIndex - 1;
        SceneManager.LoadScene(nextSceneIndex);
    }
}