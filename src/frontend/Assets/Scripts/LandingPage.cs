using UnityEngine;
using UnityEngine.UI;
using UnityEngine.SceneManagement;


public class LandingPage: MonoBehaviour{
    [SerializeField] private Button continueButton;

    private void Start() {
         continueButton.onClick.AddListener(nextScene);
    }

    private void nextScene() {
            int nextSceneIndex = SceneManager.GetActiveScene().buildIndex + 1;
            SceneManager.LoadScene(nextSceneIndex);
    }
}


