using System.Collections.Generic;
using System.IO;
using UnityEngine;
using System;
using UnityEngine.UI;
using TMPro;
using UnityEngine.SceneManagement;

public class PositionPlayback : PlaybackView
{
    [SerializeField] private RawImage carTransform;
    [SerializeField] private LineRenderer trackRenderer;
    private float previousTime;
    private Vector3 startPosition = new Vector3(-360, -132, 0);  // Adjust this to your track's start point
    private Vector3 endPosition = new Vector3(40, -132, 0);  // Adjust this to your track's end point
    private float endDistance = 141.57743448791217f;  // Adjust this to your track's length
    private float pathLength = 0f;
    InputFields inputFields;
    private float angle;

    private void Start()
    {
        inputFields = FindAnyObjectByType<InputFields>();
        angle = (float)inputFields.parameters.AngleOfIncline;
        if (angle != 0)
        {
            calcEndPosition();
        }
        pathLength = Vector3.Distance(startPosition, endPosition);
        //RenderTrackLine();
    }

    public override void Display(DataPoint dataPoint)
    {
        if (previousTime == 0 || dataPoint.Time == 0)
        {
            if (angle != 0)
            {
                UpdateAngle(angle);
            }
            previousTime = dataPoint.Time;
            carTransform.GetComponent<RectTransform>().anchoredPosition = new Vector2(startPosition.x, startPosition.y);
            return;
        }

         // Calculate elapsed time since the last update
        float elapsedTime = dataPoint.Time - previousTime;
        float distanceTraveledThisFrame = dataPoint.Velocity * elapsedTime;

        MoveCarAlongTrack(dataPoint.Position, dataPoint.Velocity);
        previousTime = dataPoint.Time;
    }

// private void RenderTrackLine()
//     {

//         Vector3 worldStart = carTransform.rectTransform.TransformPoint(startPosition);
//         Vector3 worldEnd = carTransform.rectTransform.TransformPoint(endPosition);
//         trackRenderer.positionCount = 2;
//         trackRenderer.SetPosition(0, worldStart);
//         trackRenderer.SetPosition(1, worldEnd);
//         trackRenderer.startWidth = 10f;
//         trackRenderer.endWidth = 10f;
//         trackRenderer.startColor = Color.green;
//         trackRenderer.endColor = Color.green;
//     }

    private void calcEndPosition()
    {
        float arcLength = endDistance/Mathf.Cos(angle);
        float xPosition = startPosition.x + arcLength;
        float yOffSet = arcLength * Mathf.Sin(angle);
        endPosition = new Vector3(xPosition, startPosition.y + yOffSet, 0);
        
    }

    private void MoveCarAlongTrack(float position, float velocity)
    {
        float normalizedDistance = Mathf.Clamp01(position / endDistance);

        float xPosition = Mathf.Lerp(startPosition.x, endPosition.x, normalizedDistance);
        float yPosition = Mathf.Lerp(startPosition.y, endPosition.y, normalizedDistance);
        carTransform.GetComponent<RectTransform>().anchoredPosition = new Vector2(xPosition, yPosition);
    }

    private void UpdateAngle(float angle)
    {
        // convert angle back to degrees
        carTransform.GetComponent<RectTransform>().rotation = Quaternion.Euler(0, 0, angle);
    }
}