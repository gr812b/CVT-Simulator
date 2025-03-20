using CommunicationProtocol.Receivers;

namespace CommunicationProtocolUnitTesting
{
    [TestClass]
    public class SimulationResultTest
    {
        private readonly string csvFile = "test_front_end_output.csv";

        private string CSVPath => Path.Combine(Directory.GetCurrentDirectory(), csvFile);

        [TestInitialize]
        public void SetUp()
        {
            // Write test data to the file
            File.WriteAllText(CSVPath, "time,car_velocity,car_position,shift_distance,engine_angular_position,secondary_angular_position,engine_angular_velocity\n" +
                                       "0,20,30,0.005,10,30,15\n" +
                                       "1,25,35,0.010,15,35,20\n");
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

            DataPoint firstDataPoint = simulationResult[0];
            Assert.AreEqual(0, firstDataPoint.Time, maxDifference);
            Assert.AreEqual(20, firstDataPoint.CarVelocity, maxDifference);
            Assert.AreEqual(30, firstDataPoint.CarPosition, maxDifference);
            Assert.AreEqual(1 - 0.005, firstDataPoint.PrimaryShiftDistance, maxDifference);
            Assert.AreEqual(0.005, firstDataPoint.SecondaryShiftDistance, maxDifference);
            Assert.AreEqual(10, firstDataPoint.PrimaryRotation, maxDifference);
            Assert.AreEqual(30, firstDataPoint.SecondaryRotation, maxDifference);
            Assert.AreEqual(15, firstDataPoint.EngineRPM, maxDifference);

            DataPoint secondDataPoint = simulationResult[1];
            Assert.AreEqual(1, secondDataPoint.Time, maxDifference);
            Assert.AreEqual(25, secondDataPoint.CarVelocity, maxDifference);
            Assert.AreEqual(35, secondDataPoint.CarPosition, maxDifference);
            Assert.AreEqual(1 - 0.010, secondDataPoint.PrimaryShiftDistance, maxDifference);
            Assert.AreEqual(0.010, secondDataPoint.SecondaryShiftDistance, maxDifference);
            Assert.AreEqual(15, secondDataPoint.PrimaryRotation, maxDifference);
            Assert.AreEqual(35, secondDataPoint.SecondaryRotation, maxDifference);
            Assert.AreEqual(20, secondDataPoint.EngineRPM, maxDifference);

        }
    }
}