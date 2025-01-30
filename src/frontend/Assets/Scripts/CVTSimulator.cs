using System;
using System.Collections.Generic;
using UnityEngine;

public class CVTSimulator : MonoBehaviour, IPlaybackView
{
    [SerializeField] private GameObject primaryPulley;
    
    public void Display(DataPoint dataPoint)
    {
        SetPrimaryPulleyAngle(dataPoint.PrimaryPulleyAngle);
    }

    // Sets the angle of the primary pulley based on the given angle
    private void SetPrimaryPulleyAngle(float angle)
    {
        primaryPulley.transform.localRotation = Quaternion.Euler(0, 0, angle);
    }
}