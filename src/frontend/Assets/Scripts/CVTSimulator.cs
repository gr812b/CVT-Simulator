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

    
    public override void Display(DataPoint dataPoint)
    {
        SetAngles(dataPoint.Position);
        SetShifts(dataPoint.Position);
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
}