using System.Collections.Generic;
using System.IO;

namespace CommunicationProtocol.Senders {
    public class InputStore {
        public void Store(string path, List<Parameter> parameters) {
            // Delete the file if it already exists
            if (File.Exists(path)) {
                File.Delete(path);
            }

            // Write the parameters to the file
            using (var writer = new StreamWriter(path)) {
                // write the header row
                writer.WriteLine("Name,Value");
                // write each parameter to the file
                foreach (Parameter parameter in parameters) {
                    writer.WriteLine($"{parameter.Name},{parameter.Value}");
                }
            }
        }
    }
}