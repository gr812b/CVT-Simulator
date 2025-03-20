using UnityEngine;
using System.IO;
using System.Collections.Generic;
using CommunicationProtocol.Senders;
public static class PathConstants
{
    private static string Relativize(string path)
    {
        return Path.Combine(Application.dataPath, path);
    }

    public static string SIMULATION_OUTPUT_PATH = Relativize("../front_end_output.csv");
    public static string INPUT_PARAMETERS_PATH = Relativize("../input_parameters.csv");
    public static string PYTHON_ENVIRONMENT_PATH = Relativize("../../../venv/Scripts/python.exe");
    public static string PYTHON_SCRIPT_PATH = Relativize("../../main.py");
    public static string GRAPH_SCRIPT_PATH = Relativize("../../utils/generate_graphs.py");
}

public static class ParameterNames {
    public static string FLYWEIGHT_MASS = "flyweight_mass";
    public static string PRIMARY_RAMP_GEOMETRY = "primary_ramp_geometry";
    public static string PRIMARY_SPRING_RATE = "primary_spring_rate";
    public static string PRIMARY_SPRING_PRETENSION = "primary_spring_pretension";
    public static string SECONDARY_HELIX_GEOMETRY = "secondary_helix_geometry";
    public static string SECONDARY_TORSION_SPRING_RATE = "secondary_torsion_spring_rate";
    public static string SECONDARY_COMPRESSION_SPRING_RATE = "secondary_compression_spring_rate";
    public static string SECONDARY_SPRING_PRETENSION = "secondary_spring_pretension";
    public static string VEHICLE_WEIGHT = "vehicle_weight";
    public static string DRIVER_WEIGHT = "driver_weight";
    public static string TRACTION = "traction";
    public static string ANGLE_OF_INCLINE = "angle_of_incline";
    public static string TOTAL_DISTANCE = "total_distance";
}

public static class DefaultParameters
{
    public static List<Parameter> parameters = new List<Parameter>
    {
        new Parameter(ParameterNames.FLYWEIGHT_MASS, "0.6"),
        new Parameter(ParameterNames.PRIMARY_RAMP_GEOMETRY, "0.0"),
        new Parameter(ParameterNames.PRIMARY_SPRING_RATE, "500.0"),
        new Parameter(ParameterNames.PRIMARY_SPRING_PRETENSION, "0.2"),
        new Parameter(ParameterNames.SECONDARY_HELIX_GEOMETRY, "0.0"),
        new Parameter(ParameterNames.SECONDARY_TORSION_SPRING_RATE, "100.0"),
        new Parameter(ParameterNames.SECONDARY_COMPRESSION_SPRING_RATE, "100.0"),
        new Parameter(ParameterNames.SECONDARY_SPRING_PRETENSION, "15.0"),
        new Parameter(ParameterNames.VEHICLE_WEIGHT, "225.0"),
        new Parameter(ParameterNames.DRIVER_WEIGHT, "75.0"),
        new Parameter(ParameterNames.TRACTION, "100.0"),
        new Parameter(ParameterNames.ANGLE_OF_INCLINE, "15.0"),
        new Parameter(ParameterNames.TOTAL_DISTANCE, "200")
    };
}