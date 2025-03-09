using UnityEngine;
using TMPro;
using CommunicationProtocol.Receivers;

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
        InputParameters parameters = new InputParameters(PathConstants.INPUT_PARAMETERS_PATH);
        //update the values in the UI\
        FlyweightMass_val.text = parameters.GetValue(ParameterNames.FLYWEIGHT_MASS);
        PrimaryRampGeo_val.text = parameters.GetValue(ParameterNames.PRIMARY_RAMP_GEOMETRY);
        PrimarySpringRate_val.text = parameters.GetValue(ParameterNames.PRIMARY_SPRING_RATE);
        PrimarySpringPretension_val.text = parameters.GetValue(ParameterNames.PRIMARY_SPRING_PRETENSION);
        SecondaryHelixGeo_val.text = parameters.GetValue(ParameterNames.SECONDARY_HELIX_GEOMETRY);
        SecondaryTorsionSpringRate_val.text = parameters.GetValue(ParameterNames.SECONDARY_TORSION_SPRING_RATE);
        SecondaryCompressionSpringRate_val.text = parameters.GetValue(ParameterNames.SECONDARY_COMPRESSION_SPRING_RATE);
        SecondarySpringPretension_val.text = parameters.GetValue(ParameterNames.SECONDARY_SPRING_PRETENSION);
        VehicleWeight_val.text = parameters.GetValue(ParameterNames.VEHICLE_WEIGHT);
        DriverWeight_val.text = parameters.GetValue(ParameterNames.DRIVER_WEIGHT);
        Traction_val.text = parameters.GetValue(ParameterNames.TRACTION);
        AngleofIncline_val.text = parameters.GetValue(ParameterNames.ANGLE_OF_INCLINE);
    }
 }

