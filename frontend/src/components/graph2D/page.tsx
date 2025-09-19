import { Graph2D } from './graph2D';
import { csvToDataPoints } from './csvUtils';
import csvText from "./front_end_output.csv?raw";

export function Page() {
  // Parse CSV data
  const { data, errors, warnings } = csvToDataPoints(csvText, 'time', 'car_velocity');
  
  // Log any issues
  if (warnings.length > 0) console.warn('CSV warnings:', warnings);
  if (errors.length > 0) console.error('CSV errors:', errors);
  
  return (
    <div>
      <h1>Graph2D Demo</h1>
      
      <Graph2D
        data={data}
        config={{
          title: "Velocity vs Time",
          xAxis: { name: "Time", type: "value", unit: "s" },
          yAxis: { name: "Velocity", type: "value", unit: "m/s" },
          height: 400
        }}
      />
      
      <Graph2D
        data={[]}
        config={{
          title: "Empty Data Test",
          xAxis: { name: "Time", type: "value", unit: "s" },
          yAxis: { name: "Value", type: "value" }
        }}
      />
    </div>
  );
}