using System;
using System.Collections.Generic;
using UnityEngine;

public class CVTSimulator : MonoBehaviour
{   
    private List<Tuple<float, float>> dataPoints = new List<Tuple<float, float>>();

    // References to the unity objects
    [SerializeField] private GameObject primaryPulley;


    // Pass in the data points to use for the simulation
    public void SetDataPoints(List<Tuple<float, float>> dataPoints)
    {
        this.dataPoints = dataPoints;
    }

    // Set the CVT simulation to the given time
    public void SimulateTime(float time)
    {
        // Update the primary pulley rotation
        SetPrimaryPulleyRotation(time);
    }

    // Set primary pulley rotation based on time
    private void SetPrimaryPulleyRotation(float time)
    {
        // Get the data point matching the time
        float angle = dataPoints.Find(x => x.Item1 == time).Item2;

        // Set the rotation of the primary pulley
        primaryPulley.transform.rotation = Quaternion.Euler(0, 0, angle);
    }

}
