using UnityEngine;
using TMPro;

public class LoadingBar : MonoBehaviour
{
    [SerializeField] private GameObject baseBar;
    [SerializeField] private GameObject movingBar;
    [SerializeField] private GameObject percentageTracker;
    [SerializeField] private TMP_Text percentageText;

    private float maxWidth;
    private float movingX;
    private float trackerY;


    private void Start()
    {
        // Get the width of the base bar
        maxWidth = baseBar.GetComponent<RectTransform>().rect.width;

        // Get the x position of the moving bar
        movingX = movingBar.transform.localPosition.x;

        // Set the progress to 0
        SetPercentage(0);
    }

    public void SetPercentage(float percentage)
    {
        float newWidth = maxWidth * percentage;
        SetMovingBarWidth(newWidth);
        SetTrackerPosition(newWidth);
        SetPercentageText(percentage);
    }

    private void SetMovingBarWidth(float newWidth)
    {
        // Set the new width of the moving bar
        movingBar.GetComponent<RectTransform>().SetSizeWithCurrentAnchors(RectTransform.Axis.Horizontal, newWidth);
    }

    private void SetTrackerPosition(float newWidth)
    {
        // Set the tracker's posittion to movingX + newWidth and keep the y position the same
        float currentY = percentageTracker.transform.localPosition.y;
        percentageTracker.transform.localPosition = new Vector3(movingX + newWidth, currentY, 0);
    }

    private void SetPercentageText(float percentage)
    {
        // Set the text of the percentage tracker to the percentage
        percentageText.text = $"{percentage * 100}%";
    }
}
