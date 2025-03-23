using UnityEngine;
using TMPro;

public class RampInput : MonoBehaviour
{
    [SerializeField] private TMP_InputField inputField;
    [SerializeField] private TMP_Dropdown dropdown;

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
                break;
            case "2":
                dropdown.value = 2;
                break;
            default:
                dropdown.value = 0;
                break;
        }
    }

    public void UpdateInputFromDropdown(int index)
    {
        if (inputField == null) return;

        switch (index)
        {
            case 0:
                inputField.text = "not a ramp";
                break;
            case 1:
                inputField.text = "1";
                break;
            case 2:
                inputField.text = "2";
                break;
        }
    }
}
