using CommunicationProtocol.Receivers;
using System.Diagnostics;

namespace CommunicationProtocolUnitTesting
{
    [TestClass]
    public class InputParametersTest
    {
        private readonly string csvFile = "test_input_parameters.csv";

        private string CSVPath => Path.Combine(Directory.GetCurrentDirectory(), csvFile);

        [TestInitialize]
        public void SetUp()
        {
            // Write test data to the file
            File.WriteAllText(CSVPath, "Name,Value\n" +
                                       "parameter1,1\n" +
                                       "parameter2,2\n");
        }

        [TestCleanup]
        public void TearDown()
        {
            File.Delete(CSVPath);
        }

        [TestMethod]
        public void TestLoadData()
        {
            // Get the input parameters
            InputParameters inputParameters = new InputParameters(CSVPath);

            Assert.AreEqual("1", inputParameters.GetValue("parameter1"));
            Assert.AreEqual("2", inputParameters.GetValue("parameter2"));
        }
    }
}