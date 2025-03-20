using System;

namespace CommunicationProtocol.Receivers
{
    public class DataPoint
    {
        public float Time { get; }
        public float CarPosition { get; }
        public float CarVelocity { get; }
        public float EngineRPM { get; }
        public float PrimaryRotation { get; }
        public float SecondaryRotation { get; }
        public float PrimaryShiftDistance { get; }
        public float SecondaryShiftDistance { get; }

        public DataPoint(float time, float carVelocity, float carPosition, float shiftDistance, float engineAngluarPosition, float secondaryAngularPostion, float engineAngularVelocity)
        {
            Time = time;
            CarPosition = carPosition;
            CarVelocity = carVelocity;
            EngineRPM = engineAngularVelocity;
            PrimaryRotation = engineAngluarPosition;
            SecondaryRotation = secondaryAngularPostion;
            PrimaryShiftDistance = 1 - shiftDistance;
            SecondaryShiftDistance = shiftDistance;
        }
    }

    public class SimulationResult : CSVReader<DataPoint>
    {
        public SimulationResult(string path) : base(path) { }

        protected override DataPoint ParseRow(string[] values)
        {
            float time = float.Parse(values[headerMap["time"]]);
            float carVelocity = float.Parse(values[headerMap["car_velocity"]]);
            float carPosition = float.Parse(values[headerMap["car_position"]]);
            float shiftDistance = float.Parse(values[headerMap["shift_distance"]]);
            float engineAngularPosition = float.Parse(values[headerMap["engine_angular_position"]]);
            float secondaryAngularPosition = float.Parse(values[headerMap["secondary_angular_position"]]);
            float engineAngularVelocity = float.Parse(values[headerMap["engine_angular_velocity"]]);

            return new DataPoint(time, carVelocity, carPosition, shiftDistance, engineAngularPosition, secondaryAngularPosition, engineAngularVelocity);
        }
    }
}