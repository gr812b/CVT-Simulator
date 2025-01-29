using System.Collections.Generic;
using System.IO;
using UnityEngine;
using System;
using UnityEngine.UI;
using TMPro;
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


