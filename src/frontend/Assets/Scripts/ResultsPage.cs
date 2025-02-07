using System.Diagnostics;
using System.IO;
using UnityEngine;
using UnityEngine.UI;
using TMPro;

public class ResultsPage: MonoBehaviour
{
    //values to update
    [SerializeField] TMP_Text FlyweightMass_val;
    [SerializeField] TMP_Text PrimaryRampGeo_val;
    [SerializeField] TMP_Text PrimarySpringRate_val;
    [SerializeField] TMP_Text PrimarySpringPretension_val;
    [SerializeField] TMP_Text SecondaryHelixGeo_val;
    [SerializeField] TMP_Text SecondaryTorsionSpringRate_val;
    [SerializeField] TMP_Text SecondaryCompressionSpringRate_val;
    [SerializeField] TMP_Text SecondarySpringPretension_val;
    [SerializeField] TMP_Text VehicleWeight_val;
    [SerializeField] TMP_Text DriverWeight_val;
    [SerializeField] TMP_Text Traction_val;
    [SerializeField] TMP_Text AngleofIncline_val;

    //initalize before it starts
    private void Awake()
    {
        //find InputFields 
        Parameters parameters = SimulationData.parameters; 
        //update the values in the UI
        FlyweightMass_val.text = parameters.FlyweightMass.ToString();
        PrimaryRampGeo_val.text = parameters.PrimaryRampGeometry.ToString();
        PrimarySpringRate_val.text = parameters.PrimarySpringRate.ToString();
        PrimarySpringPretension_val.text = parameters.PrimarySpringPretension.ToString();
        SecondaryHelixGeo_val.text = parameters.SecondaryHelixGeometry.ToString();
        SecondaryTorsionSpringRate_val.text = parameters.SecondaryTorsionSpringRate.ToString();
        SecondaryCompressionSpringRate_val.text = parameters.SecondaryCompressionSpringRate.ToString();
        SecondarySpringPretension_val.text = parameters.SecondarySpringPretension.ToString();
        VehicleWeight_val.text = parameters.VehicleWeight.ToString();
        DriverWeight_val.text = parameters.DriverWeight.ToString();
        Traction_val.text = parameters.Traction.ToString();
        AngleofIncline_val.text = parameters.AngleOfIncline.ToString();
    }
 }

