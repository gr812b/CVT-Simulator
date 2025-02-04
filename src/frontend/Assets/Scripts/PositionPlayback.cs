using System.Collections.Generic;
using System.IO;
using UnityEngine;
using System;
using UnityEngine.UI;
using TMPro;
using UnityEngine.SceneManagement;

public class PositionPlayback : PlaybackView
{
    [SerializeField] private Transform carTransform;

   
    private float previousTime;
    private Vector3 startPosition = new Vector3(0, 0, 0);  // Adjust this to your track's start point
    private Vector3 endPosition = new Vector3(7, 0, 0);  // Adjust this to your track's end point
    private float endDistance = 141.57743448791217f;  // Adjust this to your track's length
    private float pathLength = 0f;

    private void Start()
    {
        pathLength = Vector3.Distance(startPosition, endPosition);
    }

    public override void Display(DataPoint dataPoint)
    {
        // If it's the first data point, just set it up
        if (previousTime == 0 || dataPoint.Time == 0)
        {
            previousTime = dataPoint.Time;
            carTransform.position = startPosition;
            return;
        }

         // Calculate elapsed time since the last update
        float elapsedTime = dataPoint.Time - previousTime;
        float distanceTraveledThisFrame = dataPoint.Velocity * elapsedTime;

        MoveCarAlongTrack(dataPoint.Position, dataPoint.Velocity);
        previousTime = dataPoint.Time;
    }

    private void MoveCarAlongTrack(float position, float velocity)
    {
        // Normalize the traveled distance to fit within the expected range
        float normalizedDistance = Mathf.Clamp01(position / endDistance);

        // Scale the movement along the actual world-space path
        float worldSpaceTravel = normalizedDistance * pathLength;

        // Move the car along the track
        Vector3 newCarPosition = Vector3.Lerp(startPosition, endPosition, worldSpaceTravel / pathLength);
        carTransform.position = newCarPosition;
    }
}