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

    private void RenderTrackLine()
        {

            Vector3 worldStart = new Vector3(-7, -3, 0);
            Vector3 worldEnd = new Vector3(2, -3, 0);
            trackRenderer.positionCount = 2;
            trackRenderer.SetPosition(0, worldStart);
            trackRenderer.SetPosition(1, worldEnd);
            trackRenderer.startWidth = 10f;
            trackRenderer.endWidth = 10f;
            trackRenderer.startColor = Color.green;
            trackRenderer.endColor = Color.green;
        }

    private void calcEndPosition()
    {
        // Convert angle from degrees to radians
        float angleRad = angle * Mathf.Deg2Rad;

        // Calculate the radius of the circle based on the end distance
        float radius = endDistance / angleRad;  // Radius = arc length / angle in radians

        // Calculate the x and y position on the circle at the given angle
        float xOffset = radius * Mathf.Cos(angleRad);
        float yOffset = radius * Mathf.Sin(angleRad);

        // The end position is relative to the start position (center of the circle)
        endPosition = new Vector3(startPosition.x + xOffset, startPosition.y + yOffset, 0);
        
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