using UnityEngine;
using TMPro;
using CommunicationProtocol.Receivers.SimulationResult;

public class GaugePlayback : PlaybackView
{
    [SerializeField] private GameObject velocityNeedle;
    [SerializeField] private GameObject rpmNeedle;
    [SerializeField] private TMP_Text velocityText;
    [SerializeField] private TMP_Text rpmText;

    private float maxVelocity = 90.0f;
    private float maxRPM = 4500.0f;
     private float minGaugeAngle = 135.0f; 
    private float maxGaugeAngle = -135.0f;  

    
    public override void Display(DataPoint dataPoint)
    {
        float velocity = Mathf.Clamp(dataPoint.CarVelocity, 0, maxVelocity);  
        float rpm = Mathf.Clamp(dataPoint.EngineRPM, 0, maxRPM);
        SetVelocity(velocity);
        SetRPM(rpm);
    }

    private void SetVelocity(float velocity)
    {
        // round to 1 decimal place
        velocityText.text = velocity.ToString("F1") + " km/h";
        SetNeedle(velocityNeedle, velocity, maxVelocity);
    }

    private void SetRPM(float rpm)
    {
        // round to 1 decimal place
        rpmText.text = rpm.ToString("F1") + " RPM";
        SetNeedle(rpmNeedle, rpm, maxRPM);
    }
  
    private void SetNeedle(GameObject needle, float value, float maxValue)
    {
        float angle = Mathf.Lerp(minGaugeAngle, maxGaugeAngle, value / maxValue);
        needle.transform.localEulerAngles = new Vector3(0, 0, angle);
    }
}