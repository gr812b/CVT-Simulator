using System;
using System.Collections.Generic;
using Unity.Mathematics;
using UnityEngine;

public class CVTPlayback : PlaybackView
{
    // The pulley models
    [SerializeField] private GameObject primaryMovable;
    [SerializeField] private GameObject primaryFixed;
    [SerializeField] private GameObject secondaryMovable;
    [SerializeField] private GameObject secondaryFixed;

    // The maximum shift distance value from the backend
    private float maxShiftDistance = 0.05f;

    // The maximum distance that the pulley model can move
    private float maxPrimaryDistance = 0.3f;
    private float maxSecondaryDistance = -0.3f;
    
    public override void Display(DataPoint dataPoint)
    {
        SetAngles(dataPoint.PrimaryAngle, dataPoint.SecondaryAngle);
        SetShifts(dataPoint.ShiftDistance);
    }

    // Handles setting all of the angles for the pulley models
    private void SetAngles(float primaryAngle, float secondaryAngle)
    {
        SetAngle(ref primaryMovable, primaryAngle);
        SetAngle(ref primaryFixed, primaryAngle);
        SetAngle(ref secondaryMovable, secondaryAngle);
        SetAngle(ref secondaryFixed, secondaryAngle);
    }

    // Sets the angle of a component
    private void SetAngle(ref GameObject component, float angle)
    {
        component.transform.localRotation = Quaternion.identity;
        component.transform.Rotate(angle, 0, 0);
    }

    // Handles setting the shift distance for the pulley models
    private void SetShifts(float shiftDistance)
    {
        SetShiftDistance(ref primaryMovable, maxPrimaryDistance, maxShiftDistance - shiftDistance); // Invert distance
        SetShiftDistance(ref secondaryMovable, maxSecondaryDistance, shiftDistance); 
    }

    // Sets the shift distance of a movable component
    private void SetShiftDistance(ref GameObject movableComponent, float maxComponentDistance, float shiftDistance)
    {
        float componentDistance = maxComponentDistance * shiftDistance / maxShiftDistance;
        Vector3 currentPosition = movableComponent.transform.localPosition;
        movableComponent.transform.localPosition = new Vector3(componentDistance, currentPosition.y, currentPosition.z);
    }
    
}