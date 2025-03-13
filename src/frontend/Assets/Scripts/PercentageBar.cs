using UnityEngine;
using TMPro;

public abstract class PercentageBar: MonoBehaviour
{
    [SerializeField] protected GameObject baseBar;
    [SerializeField] protected GameObject movingBar;
    [SerializeField] protected GameObject percentageTracker;

    protected float maxWidth;


    private void Start()
    {
        // Get the width of the base bar
        maxWidth = baseBar.GetComponent<RectTransform>().rect.width;

        // Set the progress to 0
        SetPercentage(0);
    }

    public void SetPercentage(float percentage)
    {
        float newWidth = maxWidth * percentage;
        SetMovingBarWidth(newWidth);
        SetTrackerPosition(newWidth);
        UpdatePercentageTracker(percentage);
    }

    private void SetMovingBarWidth(float newWidth)
    {
        // Set the new width of the moving bar
        movingBar.GetComponent<RectTransform>().SetSizeWithCurrentAnchors(RectTransform.Axis.Horizontal, newWidth);
    }

    private void SetTrackerPosition(float newWidth)
    {
        // Set the position of the percentage tracker to the end of the moving bar
        percentageTracker.GetComponent<RectTransform>().anchoredPosition = new Vector2(newWidth, 0);
    }

    protected abstract void UpdatePercentageTracker(float percentage);
}

public class LoadingBar : PercentageBar
{
    protected override void UpdatePercentageTracker(float percentage)
    {
        // Update the child component text to display the percentage
        percentageTracker.GetComponent<TMP_Text>().text = (percentage * 100).ToString("F0") + "%";
    }
}
