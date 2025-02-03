using UnityEngine;
using UnityEngine.UI;
using TMPro;

public class GaugeScript : MonoBehaviour
{
    [SerializeField] private GameObject speed_needle;
    [SerializeField] TMP_Text speed_val;
    private float car_velocity = 0;
    private float max_car_velocity = 70;

    //rpm
    [SerializeField] private GameObject rpm_needle;
    [SerializeField] TMP_Text rpm_val;
    private float rpm = 0;
    private float max_car_rpm = 3600;

    private float gaugerange = 270;

    //note 135 is zero in z
    //note -135 is 70km/h
    // Start is called once before the first execution of Update after the MonoBehaviour is created
    void Start()
    {
        setSpeed();
        setRpm();
    }

     // Update is called once per frame
    void Update()
    {
        setSpeedNeedle();
        setRpmNeedle();
    }

    //would take in car velocity or call backend
    public void setSpeed()
    {
        car_velocity = 10;
        speed_val.text = car_velocity + " km/hour";
    }

    public void setRpm()
    {
        rpm = 2000;
        rpm_val.text =  rpm + " rpm";
    }

    void setSpeedNeedle()
    {
        speed_needle.transform.localEulerAngles = new Vector3(0,0,((car_velocity/max_car_velocity)*gaugerange -135) *-1);
    }

    void setRpmNeedle()
    {
        rpm_needle.transform.localEulerAngles = new Vector3(0,0,((rpm/max_car_rpm)*gaugerange -135) *-1);
    }
}
