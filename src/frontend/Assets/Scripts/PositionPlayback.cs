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

    private float totalDistance;
    private float previousTime;
    private Vector3 startPosition = new Vector3(0, 0, 0);
    private Vector3 endPosition = new Vector3(5, 0, 0);  // Adjust this to your track's end point

    private float distanceTraveledSoFar = 0f;

    public override void Display(DataPoint dataPoint)
    {
        // If it's the first data point, just set it up
        if (previousTime == 0 || dataPoint.Time == 0)
        {
            previousTime = dataPoint.Time;
            startPosition = carTransform.position;
            return;
        }

        float elapsedTime = dataPoint.Time - previousTime;
        float distanceTraveledThisFrame = dataPoint.Velocity * elapsedTime;
        distanceTraveledSoFar += distanceTraveledThisFrame;  // Keep track of the total distance traveled

        MoveCarAlongTrack(distanceTraveledSoFar);
        previousTime = dataPoint.Time;
    }

    private void MoveCarAlongTrack(float totalDistanceTraveled)
    {
        // Calculate how far along the path the car has traveled
        float pathLength = Vector3.Distance(startPosition, endPosition);

        // If total distance traveled is greater than path length, clamp it to the end point
        totalDistanceTraveled = Mathf.Min(totalDistanceTraveled, pathLength);

        // Interpolate the car's position along the track based on the accumulated distance
        float t = totalDistanceTraveled / pathLength;

        // Interpolate between the start and end positions based on the accumulated traveled distance
        Vector3 newCarPosition = Vector3.Lerp(startPosition, endPosition, t);
        carTransform.position = newCarPosition;
    }
}