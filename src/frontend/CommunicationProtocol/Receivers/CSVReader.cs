using System.Collections.Generic;
using System.IO;

namespace CommunicationProtocol
{
    namespace Receivers
    {
        public abstract class CSVReader<T> : List<T>
        {
            // Constructor to load data when instantiated
            public CSVReader(string path)
            {
                LoadData(path);
            }

            // Parsing method to be implemented by subclasses
            public abstract T ParseRow(string[] values);

            // Method to read all data from the CSV file
            public void LoadData(string path)
            {
                // Clear existing data
                this.Clear();

                // Read the CSV file line by line and parse each row using the concrete implementation of ParseRow
                using (var reader = new StreamReader(path))
                {
                    // Skip the header row
                    reader.ReadLine();

                    while (!reader.EndOfStream)
                    {
                        var line = reader.ReadLine();
                        var values = line.Split(',');

                        this.Add(ParseRow(values));
                    }
                }
            }
        }
    }
}
