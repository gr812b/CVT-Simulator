using System;

namespace CommunicationProtocol.Receivers
{
    public class DataPoint
    {
        public float Time { get; }
        public float CarPosition { get; }
        public float CarVelocity { get; }
        public float EngineRPM { get; }
        public float PrimaryAngle { get; }
        public float SecondaryAngle { get; }
        public float PrimaryShiftDistance { get; }
        public float SecondaryShiftDistance { get; }

        private readonly float maxShiftDistance = 0.026f;

        public DataPoint(float time, float engineAngularVelocity, float engineAngularPosition, float carVelocity, float carPosition, float shiftDistance)
        {
            Time = time;
            CarPosition = carPosition;
            PrimaryAngle = RadiansToDegrees(engineAngularPosition);
            SecondaryAngle = RadiansToDegrees(CarPositionToSecondaryAngle(carPosition)); ;
            CarVelocity = MetersPerSecondToKmPerHour(carVelocity);
            EngineRPM = RadPerSecondToRPM(engineAngularVelocity);

            float shiftPercentage = shiftDistance / maxShiftDistance;
            PrimaryShiftDistance = 1 - shiftPercentage;
            SecondaryShiftDistance = shiftPercentage;
        }

        private float RadiansToDegrees(float radians)
        {
            float degreesPerRadian = 180.0f / (float)Math.PI;
            return radians * degreesPerRadian;
        }

        private float CarPositionToSecondaryAngle(float position)
        {
            return position * (2.0f * 7.556f) / (22.0f * 0.0254f);
        }

        private float RadPerSecondToRPM(float radPerSecond)
        {
            float RPMPerRad = 60.0f / (2.0f * (float)Math.PI);
            return radPerSecond * RPMPerRad;
        }

        private float MetersPerSecondToKmPerHour(float metersPerSecond)
        {
            float kmPerMeter = 0.001f;
            float secondsPerHour = 3600.0f;
            return metersPerSecond * kmPerMeter * secondsPerHour;
        }
    }

    public class SimulationResult : CSVReader<DataPoint>
    {
        public SimulationResult(string path) : base(path) { }

        protected override DataPoint ParseRow(string[] values)
        {
            float time = float.Parse(values[0]);
            float engineAngularVelocity = float.Parse(values[1]);
            float engineAngularPosition = float.Parse(values[2]);
            float carVelocity = float.Parse(values[3]);
            float carPosition = float.Parse(values[4]);
            float shiftDistance = float.Parse(values[6]);

            return new DataPoint(time, engineAngularVelocity, engineAngularPosition, carVelocity, carPosition, shiftDistance);
        }
    }
}