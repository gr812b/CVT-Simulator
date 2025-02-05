using System.Collections.Generic;
using System.IO;
using UnityEngine;
using System;
using UnityEngine.UI;
using TMPro;
using UnityEngine.SceneManagement;

public class GaugePlayback : PlaybackView
{
    [SerializeField] private GameObject velocityNeedle;
    [SerializeField] private GameObject rpmNeedle;
    [SerializeField] private TMP_Text velocityText;
    [SerializeField] private TMP_Text rpmText;

    private float maxVelocity = 70.0f;
    private float maxRPM = 6000.0f;
     private float minGaugeAngle = 135.0f; 
    private float maxGaugeAngle = -135.0f;  

    
    public override void Display(DataPoint dataPoint)
    {
        float velocity = Mathf.Clamp(dataPoint.Velocity, 0, maxVelocity);  
        //given angular velocity in rad/s, convert to rpm
        float rpm = Mathf.Clamp(dataPoint.AngularVelocity * 60 / (2 * Mathf.PI), 0, maxRPM);
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