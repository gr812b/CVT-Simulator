using System;
using System.Collections.Generic;
using Unity.Mathematics;
using UnityEngine;

public class CVTPlayback : PlaybackView
{
    [SerializeField] private GameObject primaryMovable;
    [SerializeField] private GameObject primaryFixed;
    [SerializeField] private GameObject secondaryMovable;
    [SerializeField] private GameObject secondaryFixed;

    // The maximum shift distance value from the backend
    private float maxShiftDistance = 1.0f;

    // The maximum distance that the pulley model can move
    private float maxPrimaryDistance = 0.3f;
    private float maxSecondaryDistance = -0.3f;
    
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
        component.transform.localRotation = Quaternion.identity;
        component.transform.Rotate(angle, 0, 0);
    }

    private void SetShifts(float distance)
    {
        SetShiftDistance(ref primaryMovable, maxPrimaryDistance, distance);
        SetShiftDistance(ref secondaryMovable, maxSecondaryDistance, maxShiftDistance - distance); // Invert distance
    }

    private void SetShiftDistance(ref GameObject movableComponent, float maxComponentDistance, float distance)
    {
        float shiftDistance = maxComponentDistance * distance / maxShiftDistance;
        Vector3 currentPosition = movableComponent.transform.localPosition;
        movableComponent.transform.localPosition = new Vector3(shiftDistance, currentPosition.y, currentPosition.z);
    }
    
}