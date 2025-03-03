using NUnit.Framework;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using DataLoader;

[TestFixture]
public class CSVReaderTest
{
    private CSVReader csvReader;
    private string csvPath;

    [SetUp]
    public void SetUp()
    {
        csvReader = new CSVReader();
        csvPath = Path.Combine(Application.dataPath, "../simulation_output.csv");

        // Create a test CSV file
        File.WriteAllText(csvPath, "time,engine_angular_velocity,engine_angular_position,car_velocity,car_position,shift_distance\n" +
                                      "0,10,0.1,20,30,0.005\n" +
                                      "1,15,0.2,25,35,0.010\n");
    }

    [TearDown]
    public void TearDown()
    {
        // Clean up the test CSV file
        if (File.Exists(csvPath))
        {
            File.Delete(csvPath);
        }
    }

    [Test]
    public void TestLoadCSVData()
    {
        List<DataPoint> dataPoints = csvReader.LoadCSVData();

        Assert.AreEqual(2, dataPoints.Count);

        DataPoint firstPoint = dataPoints[0];
        Assert.AreEqual(0, firstPoint.Time);
        Assert.AreEqual(10 * 60 / (2 * Mathf.PI), firstPoint.EngineRPM);
        Assert.AreEqual(0.1f * 180.0f / Mathf.PI, firstPoint.PrimaryAngle);
        Assert.AreEqual(30 * (2.0f * 7.556f) / (22.0f * 0.0254f), firstPoint.SecondaryAngle);
        Assert.AreEqual(20 * 3.6f, firstPoint.CarVelocity);
        Assert.AreEqual(1 - 0.005f / 0.017f, firstPoint.PrimaryShiftDistance);
        Assert.AreEqual(0.005f / 0.017f, firstPoint.SecondaryShiftDistance);

        DataPoint secondPoint = dataPoints[1];
        Assert.AreEqual(1, secondPoint.Time);
        Assert.AreEqual(15 * 60 / (2 * Mathf.PI), secondPoint.EngineRPM);
        Assert.AreEqual(0.2f * 180.0f / Mathf.PI, secondPoint.PrimaryAngle);
        Assert.AreEqual(35 * (2.0f * 7.556f) / (22.0f * 0.0254f), secondPoint.SecondaryAngle);
        Assert.AreEqual(25 * 3.6f, secondPoint.CarVelocity);
        Assert.AreEqual(1 - 0.010f / 0.017f, secondPoint.PrimaryShiftDistance);
        Assert.AreEqual(0.010f / 0.017f, secondPoint.SecondaryShiftDistance);
    }
}