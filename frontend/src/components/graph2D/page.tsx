import { Graph2D } from './graph2D';

export function Page() {
  // Sample data for demonstration
  const xData = [0, 1, 2, 3, 4, 5];
  const yData = [0, 10, 20, 30, 40, 50];

  return (
    <div>
      <h1>Graph2D Demo</h1>
      
      <Graph2D
        xData={xData}
        yData={yData}
        config={{
          title: "Velocity vs Time",
          xAxis: { name: "Time", type: "value", unit: "s" },
          yAxis: { name: "Velocity", type: "value", unit: "m/s" },
          height: 400
        }}
      />
      
      <Graph2D
        xData={[]}
        yData={[]}
        config={{
          title: "Empty Data Test",
          xAxis: { name: "Time", type: "value", unit: "s" },
          yAxis: { name: "Value", type: "value" }
        }}
      />
    </div>
  );
}