using System.Collections.Generic;
using System.IO;

namespace CommunicationProtocol.Receivers
{
    public abstract class CSVReader<T> : List<T>
    {
        protected Dictionary<string, int> headerMap = new Dictionary<string, int>();

        // Constructor to load data when instantiated
        public CSVReader(string path)
        {
            LoadData(path);
        }

        // Parsing method to be implemented by subclasses
        protected abstract T ParseRow(string[] values);

        // Method to read all data from the CSV file
        private void LoadData(string path)
        {
            // Clear existing data
            this.Clear();

            // Read the CSV file line by line and parse each row using the concrete implementation of ParseRow
            using (var reader = new StreamReader(path))
            {

                // Read the header row and store the index of each column
                var header = reader.ReadLine();
                var headerValues = header.Split(',');
                for (int i = 0; i < headerValues.Length; i++)
                {
                    headerMap[headerValues[i]] = i;
                }

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

