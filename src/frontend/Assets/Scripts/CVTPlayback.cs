using CommunicationProtocol.Receivers;
using UnityEngine;

public class CVTPlayback : PlaybackView
{
    // The pulley models
    [SerializeField] private GameObject primaryMovable;
    [SerializeField] private GameObject primaryFixed;
    [SerializeField] private GameObject secondaryMovable;
    [SerializeField] private GameObject secondaryFixed;

    // The maximum distance that the pulley model can move
    private float maxPrimaryDistance = 0.3f;
    private float maxSecondaryDistance = -0.3f;
    
    public override void Display(DataPoint dataPoint)
    {
        SetAngles(dataPoint.PrimaryRotation, dataPoint.SecondaryRotation);
        SetShifts(dataPoint.PrimaryShiftDistance, dataPoint.SecondaryShiftDistance);
    }

    // Handles setting all of the angles for the pulley models
    private void SetAngles(float primaryRotation, float secondaryRotation)
    {
        SetAngle(ref primaryMovable, primaryRotation);
        SetAngle(ref primaryFixed, primaryRotation);
        SetAngle(ref secondaryMovable, secondaryRotation);
        SetAngle(ref secondaryFixed, secondaryRotation);
    }

    // Sets the angle of a component
    private void SetAngle(ref GameObject component, float angle)
    {
        component.transform.localRotation = Quaternion.identity;
        component.transform.Rotate(angle, 0, 0);
    }

    // Handles setting the shift distance for the pulley models
    private void SetShifts(float primaryShiftDistance, float secondaryShiftDistance)
    {
        SetShiftDistance(ref primaryMovable, maxPrimaryDistance, primaryShiftDistance);
        SetShiftDistance(ref secondaryMovable, maxSecondaryDistance, secondaryShiftDistance); 
    }

    // Sets the shift distance of a movable component
    private void SetShiftDistance(ref GameObject movableComponent, float maxComponentDistance, float shiftDistance)
    {
        float componentDistance = maxComponentDistance * shiftDistance;
        Vector3 currentPosition = movableComponent.transform.localPosition;
        movableComponent.transform.localPosition = new Vector3(componentDistance, currentPosition.y, currentPosition.z);
    }
    
}