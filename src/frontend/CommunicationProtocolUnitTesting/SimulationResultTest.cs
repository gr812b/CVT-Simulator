using CommunicationProtocol.Receivers;

namespace CommunicationProtocolUnitTesting
{
    [TestClass]
    public class SimulationResultTest
    {
        private readonly string csvFile = "test_simulation_output.csv";

        private string CSVPath => Path.Combine(Directory.GetCurrentDirectory(), csvFile);

        [TestInitialize]
        public void SetUp()
        {
            // Write test data to the file
            File.WriteAllText(CSVPath, "time,engine_angular_velocity,engine_angular_position,car_velocity,car_position,shift_distance\n" +
                                       "0,10,0.1,20,30,0,0.005\n" +
                                       "1,15,0.2,25,35,0,0.010\n");
        }

        [TestCleanup]
        public void TearDown()
        {
            File.Delete(CSVPath);
        }

        [TestMethod]
        public void TestLoadData()
        {
            // Get the simulation result
            float maxDifference = 0.001f;
            SimulationResult simulationResult = new SimulationResult(CSVPath);
            float maxShiftDistance = 0.026f;

            DataPoint firstDataPoint = simulationResult[0];
            float estimatedTime = 0f;
            float estimatedCarPosition = 30f;
            float estimatedCarVelocity = 20f * 3.6f;
            float estimatedEngineRPM = 10f * 60f / (2f * (float)Math.PI);
            float estimatedPrimaryAngle = 0.1f * 180f / (float)Math.PI;
            float estimatedSecondaryAngle = 30f * (2.0f * 7.556f) / (22.0f * 0.0254f) * (180f / (float)Math.PI);
            float estimatedShiftPercentage = 0.005f / maxShiftDistance;
            float estimatedPrimaryShiftDistance = 1 - estimatedShiftPercentage;
            float estimatedSecondaryShiftDistance = estimatedShiftPercentage;

            Assert.AreEqual(estimatedTime, firstDataPoint.Time, maxDifference);
            Assert.AreEqual(estimatedCarPosition, firstDataPoint.CarPosition, maxDifference);
            Assert.AreEqual(estimatedCarVelocity, firstDataPoint.CarVelocity, maxDifference);
            Assert.AreEqual(estimatedEngineRPM, firstDataPoint.EngineRPM, maxDifference);
            Assert.AreEqual(estimatedPrimaryAngle, firstDataPoint.PrimaryAngle, maxDifference);
            Assert.AreEqual(estimatedSecondaryAngle, firstDataPoint.SecondaryAngle, maxDifference);
            Assert.AreEqual(estimatedPrimaryShiftDistance, firstDataPoint.PrimaryShiftDistance, maxDifference);
            Assert.AreEqual(estimatedSecondaryShiftDistance, firstDataPoint.SecondaryShiftDistance, maxDifference);

            DataPoint secondDataPoint = simulationResult[1];
            estimatedTime = 1f;
            estimatedCarPosition = 35f;
            estimatedCarVelocity = 25f * 3.6f;
            estimatedEngineRPM = 15f * 60f / (2f * (float)Math.PI);
            estimatedPrimaryAngle = 0.2f * 180f / (float)Math.PI;
            estimatedSecondaryAngle = 35f * (2.0f * 7.556f) / (22.0f * 0.0254f) * (180f / (float)Math.PI);
            estimatedShiftPercentage = 0.010f / maxShiftDistance;
            estimatedPrimaryShiftDistance = 1 - estimatedShiftPercentage;
            estimatedSecondaryShiftDistance = estimatedShiftPercentage;

            Assert.AreEqual(estimatedTime, secondDataPoint.Time, maxDifference);
            Assert.AreEqual(estimatedCarPosition, secondDataPoint.CarPosition, maxDifference);
            Assert.AreEqual(estimatedCarVelocity, secondDataPoint.CarVelocity, maxDifference);
            Assert.AreEqual(estimatedEngineRPM, secondDataPoint.EngineRPM, maxDifference);
            Assert.AreEqual(estimatedPrimaryAngle, secondDataPoint.PrimaryAngle, maxDifference);
            Assert.AreEqual(estimatedSecondaryAngle, secondDataPoint.SecondaryAngle, maxDifference);
            Assert.AreEqual(estimatedPrimaryShiftDistance, secondDataPoint.PrimaryShiftDistance, maxDifference);
            Assert.AreEqual(estimatedSecondaryShiftDistance, secondDataPoint.SecondaryShiftDistance, maxDifference);
        }
    }
}