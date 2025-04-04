using UnityEngine;
using TMPro;
using UnityEngine;
using UnityEngine.UI;
using TMPro;
using UnityEngine.SceneManagement;
using System.IO;
using System.Collections;

public class RampInput : MonoBehaviour
{
    [SerializeField] private TMP_InputField inputField;
    [SerializeField] private TMP_Dropdown dropdown;
    [SerializeField] private RawImage rampImage1;
    [SerializeField] private RawImage rampImage2;


    private void Start()
    {
        // Wait briefly, then update dropdown based on input field
        Invoke("UpdateDropdownFromInput", 0.1f);

        // Listen for dropdown changes
        dropdown.onValueChanged.AddListener(UpdateInputFromDropdown);
    }

    public void UpdateDropdownFromInput()
    {
        if (inputField == null || dropdown == null) return;

        switch (inputField.text)
        {
            case "1":
                dropdown.value = 1;
                rampImage1.gameObject.SetActive(true);
                rampImage2.gameObject.SetActive(false);
                break;
            case "2":
                dropdown.value = 2;
                rampImage1.gameObject.SetActive(false);
                rampImage2.gameObject.SetActive(true);
                break;
            default:
                dropdown.value = 0;
                rampImage1.gameObject.SetActive(false);
                rampImage2.gameObject.SetActive(false);
                break;
        }

        // Update the ramp image
        

    }

    public void UpdateInputFromDropdown(int index)
    {
        if (inputField == null) return;

        switch (index)
        {
            case 0:
                inputField.text = "not a ramp";
                rampImage1.gameObject.SetActive(false);
                rampImage2.gameObject.SetActive(false);
                break;
            case 1:
                inputField.text = "1";
                rampImage1.gameObject.SetActive(true);
                rampImage2.gameObject.SetActive(false);
                break;
            case 2:
                inputField.text = "2";
                rampImage1.gameObject.SetActive(false);
                rampImage2.gameObject.SetActive(true);
                break;
        }
    }
}
