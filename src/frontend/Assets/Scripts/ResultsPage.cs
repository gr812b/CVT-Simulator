using System.Diagnostics;
using System.IO;
using UnityEngine;
using UnityEngine.UI;
using TMPro;

public class ResultsPage: MonoBehaviour
{
    //values to update
    [SerializeField] TMP_Text Primaryweight_val;
    [SerializeField] TMP_Text PrimaryRamoGeo_val;
    [SerializeField] TMP_Text PrimarySpringRate_val;
    [SerializeField] TMP_Text PrimarySpringPretension_val;
    [SerializeField] TMP_Text SecondaryHelixGeo_val;
    [SerializeField] TMP_Text SecondarySpringRate_val;
    [SerializeField] TMP_Text SecondarySpringPretension_val;
    [SerializeField] TMP_Text VehicleWeight_val;
    [SerializeField] TMP_Text DriverWeight_val;
    [SerializeField] TMP_Text Traction_val;
    [SerializeField] TMP_Text AngleofIncline_val;

    //initalize before it starts
    private void Awake()
    {

        //find InputFields 

        //InputFields inputFields = FindObjectOfType<InputFields>();
        InputFields inputFields = FindAnyObjectByType<InputFields>();
        if (inputFields != null)
        {
            //update the values in the UI
            Primaryweight_val.text = (inputFields.parameters.PrimaryWeight).ToString();
            PrimaryRamoGeo_val.text = (inputFields.parameters.PrimaryRampGeometry).ToString();
            PrimarySpringRate_val.text = (inputFields.parameters.PrimarySpringRate).ToString();
            PrimarySpringPretension_val.text = (inputFields.parameters.PrimarySpringPretension).ToString();
            SecondaryHelixGeo_val.text = (inputFields.parameters.SecondaryHelixGeometry).ToString();
            SecondarySpringRate_val.text = (inputFields.parameters.SecondarySpringRate).ToString();
            SecondarySpringPretension_val.text = (inputFields.parameters.SecondarySpringPretension).ToString();
            VehicleWeight_val.text = (inputFields.parameters.VehicleWeight).ToString();
            DriverWeight_val.text = (inputFields.parameters.DriverWeight).ToString();
            Traction_val.text = (inputFields.parameters.Traction).ToString();
            AngleofIncline_val.text = (inputFields.parameters.AngleOfIncline).ToString();
        }
    }
}
