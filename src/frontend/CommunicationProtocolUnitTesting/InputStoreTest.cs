using CommunicationProtocol.Senders;

namespace CommunicationProtocolUnitTesting {
    [TestClass]
    public class InputStoreTest
    {
        private readonly string csvFile = "test_input_parameters.csv";

        private string CSVPath => Path.Combine(Directory.GetCurrentDirectory(), csvFile);

        [TestInitialize]
        public void SetUp()
        {
            // Initialize the input store
            InputStore inputStore = new InputStore();

            // Create the parameters to be stored
            List<Parameter> parameters = new List<Parameter>
            {
                new Parameter("parameter1", "1"),
                new Parameter("parameter2", "2")
            };

            // Store the parameters
            inputStore.Store(CSVPath, parameters);
        }

        [TestCleanup]
        public void TearDown()
        {
            File.Delete(CSVPath);
        }

        [TestMethod]
        public void TestStoreData()
        {
            // Read the stored data
            string[] lines = File.ReadAllLines(CSVPath);

            // Check the header row
            Assert.AreEqual("Name,Value", lines[0]);

            // Check the first parameter
            Assert.AreEqual("parameter1,1", lines[1]);

            // Check the second parameter
            Assert.AreEqual("parameter2,2", lines[2]);
        }
    }
}