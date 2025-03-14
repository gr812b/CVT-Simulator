using UnityEngine;
using CommunicationProtocol.Receivers;
using UnityEngine.SceneManagement;
using System.Linq;

public class LoadingPage : MonoBehaviour
{
    [SerializeField] private LoadingBar loadingBar;
    private PercentValue percentValue;
    private float currentPercent = 0;

    // Start is called once before the first execution of Update after the MonoBehaviour is created
    private void Start() => loadingBar.SetPercentage(currentPercent);

    // Update is called once per frame
    private void Update() => UpdatePercent();

    private void UpdatePercent()
    {
        percentValue = new PercentValue(PathConstants.PERCENT_VALUE_PATH);

        // Get last value of percent from the array
        float percent = percentValue.Last();

        if (percent >= 1){
            NextScene();
        } else if (percent > currentPercent){
            currentPercent = percent;
            loadingBar.SetPercentage(currentPercent);
        }
    }

    private void NextScene()
    {
        int nextSceneIndex = SceneManager.GetActiveScene().buildIndex + 1;
        SceneManager.LoadScene(nextSceneIndex);
    }
}
