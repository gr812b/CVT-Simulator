using UnityEngine;
using UnityEngine.UI;
using TMPro;
using UnityEngine.SceneManagement;
using System.IO;
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
    [SerializeField] private TMP_Text statusText;
    [SerializeField] private PlaybackView[] playbackViews;
    [SerializeField] private RawImage playImage;
    [SerializeField] private RawImage pauseImage;


    private bool isPlaying = false;
    private int currentIndex = 0;
    private float startTime;
    private float pauseTime;

    private void Start()
    {

        statusText.text = "Data Loaded. Ready to Play.";
        playPauseButton.onClick.AddListener(TogglePlayPause);
        restartButton.onClick.AddListener(RestartPlayback);
        nextSceneButton.onClick.AddListener(backButton);

        // Get path to simulation result file and then read it
        string path = Path.Combine(Application.dataPath, "../simulation_output.csv");
        simulationResult = new SimulationResult(path);
    }

    void TogglePlayPause()
    {
        if (simulationResult.Count == 0) return;

        isPlaying = !isPlaying; 

        if (isPlaying)
        {
            startTime += Time.time - pauseTime;
            statusText.text = "Playing";
            playImage.gameObject.SetActive(false);
            pauseImage.gameObject.SetActive(true);
            StartCoroutine(PlaybackCoroutine());
        }
        else
        {
            statusText.text = "Paused";
            pauseTime = Time.time;
            playImage.gameObject.SetActive(true);  
            pauseImage.gameObject.SetActive(false); 
        }
    }

    private void RestartPlayback()
    {
        isPlaying = false;
        statusText.text = "Data Loaded. Ready to Play.";
        currentIndex = 0;
        startTime = 0f;   
        pauseTime = 0f;   
        playImage.gameObject.SetActive(true);  
        pauseImage.gameObject.SetActive(false); 
    }

    private System.Collections.IEnumerator PlaybackCoroutine()
    {
        while (isPlaying && currentIndex < simulationResult.Count - 1)
        {
            if (isPlaying)
            {
                float elapsedTime = Time.time - startTime;
                
                // Move to the next data point if enough time has passed
                while (currentIndex < simulationResult.Count - 1 && elapsedTime >= simulationResult[currentIndex + 1].Time)
                {
                    // Updates views to the current index and then moves to the next index
                    UpdateViews();
                    currentIndex++;
                    if (currentIndex == simulationResult.Count - 2)
                {
                    statusText.text = "Playback Finished";
                }
                }
            }

            yield return null;
        }
        
      
        isPlaying = false;
    }

    // Updates all playback views with the current data point
    private void UpdateViews()
    {
        foreach (PlaybackView view in playbackViews)
        {
            view.Display(simulationResult[currentIndex]);
        }
    }

    // Returns to the previous scene
    private void backButton()
        {
            int nextSceneIndex = SceneManager.GetActiveScene().buildIndex - 2;
            SceneManager.LoadScene(nextSceneIndex);
        }
}


