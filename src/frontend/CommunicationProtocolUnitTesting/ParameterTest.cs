using CommunicationProtocol.Senders;

namespace CommunicationProtocolUnitTesting
{
    [TestClass]
    public class ParameterTest
    {
        Parameter parameter = new Parameter("parameter1", "1");

        [TestMethod]
        public void TestGenerateArgumentString()
        {
            Assert.AreEqual(" --parameter1 1", parameter.GenerateArgumentString());
        }
    }
}
