using System;
using System.Collections.Generic;
using Unity.Mathematics;
using UnityEngine;

public class CVTSimulator : PlaybackView
{
    [SerializeField] private GameObject primaryMovable;
    [SerializeField] private GameObject primaryFixed;
    [SerializeField] private GameObject secondaryMovable;
    [SerializeField] private GameObject secondaryFixed;

    private float maxPrimaryShift = -0.5f;
    private float minPrimaryShift = 0.0f;
    private float maxSecondaryShift = 0.5f;
    private float minSecondaryShift = 0.0f;
    private float maxDistance = 1.0f;

    private List<DataPoint> dataPoints = new List<DataPoint>();
    private int currentIndex = 0;

    
    public override void Display(DataPoint dataPoint)
    {
        SetAngles(dataPoint.Angle);
        SetShifts(dataPoint.Distance);
    }

    private void SetAngles(float angle)
    {
        SetAngle(ref primaryMovable, angle);
        SetAngle(ref primaryFixed, angle);
        SetAngle(ref secondaryMovable, angle);
        SetAngle(ref secondaryFixed, angle);
    }

    private void SetAngle(ref GameObject component, float angle)
    {
        Vector3 currentRotation = component.transform.localEulerAngles;
        component.transform.localEulerAngles = new Vector3(currentRotation.x, angle, currentRotation.z);
    }

    private void SetShifts(float distance)
    {
        SetShiftDistance(ref primaryMovable, maxPrimaryShift, minPrimaryShift, distance);
        SetShiftDistance(ref secondaryMovable, maxSecondaryShift, minSecondaryShift, maxDistance - distance);
    }

    private void SetShiftDistance(ref GameObject movableComponent, float maxShift, float minShift, float distance)
    {
        float shift = math.lerp(minShift, maxShift, distance/maxDistance);
        Vector3 currentPosition = movableComponent.transform.localPosition;
        movableComponent.transform.localPosition = new Vector3(currentPosition.x, shift, currentPosition.z);
    }

     private void Start()
    {
        for (int i = 0; i < 360; i++)
        {
            dataPoints.Add(new DataPoint(0, 0, i, (float)math.abs((180 - i) / 180.0)));
        }
    }

    private void Update()
    {
        if (currentIndex < dataPoints.Count)
        {
            Display(dataPoints[currentIndex]);
            currentIndex++;
        } else {
            currentIndex = 0;
        }
    }
}