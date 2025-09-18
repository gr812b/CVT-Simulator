// example usage
import csvText from "./front_end_output.csv?raw";
import { Graph2D } from "./graph2D";

export function Page() {
  console.log("CSV Text:", csvText);
  return <Graph2D csvText={csvText} title="Speed vs Time" height={380} />;
}
