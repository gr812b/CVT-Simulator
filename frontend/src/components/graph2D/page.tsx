import { useEffect } from 'react';
import { Graph2D } from './graph2D';
import { useState } from 'react';

export function Page() {
  // First dataset: Sine wave
  const xData = Array.from({ length: 1000 }, (_, i) => i);
  const yData = xData.map(x => Math.sin(x * 0.01) * 50 + 50);

  // Second dataset: Circle shape
  const numPoints = 1000;
  const angleStep = (2 * Math.PI) / numPoints;
  const radius = 50;
  const centerX = 50;
  const centerY = 50;
  const xDataCircle = Array.from({ length: numPoints }, (_, i) =>
    centerX + radius * Math.cos(i * angleStep)
  );
  const yDataCircle = Array.from({ length: numPoints }, (_, i) =>
    centerY + radius * Math.sin(i * angleStep)
  );

  // State to track the active index for sine wave
  const [activeIndex, setActiveIndex] = useState(0);
  // State to track the active index for circle
  const [activeIndexCircle, setActiveIndexCircle] = useState(0);

  // Increment the active index every millisecond for sine wave
  useEffect(() => {
    const interval = setInterval(() => {
      setActiveIndex((prevIndex) => (prevIndex + 1) % xData.length);
    }, 1);
    return () => clearInterval(interval);
  }, [xData.length]);

  // Increment the active index every millisecond for circle
  useEffect(() => {
    const interval = setInterval(() => {
      setActiveIndexCircle((prevIndex) => (prevIndex + 1) % xDataCircle.length);
    }, 1);
    return () => clearInterval(interval);
  }, [xDataCircle.length]);

  return (
    <div>
      <h1>Graph2D Demo</h1>
      
      <Graph2D
        xData={xData}
        yData={yData}
        activeIndex={activeIndex}
        config={{
          title: "Velocity vs Time",
          xAxis: { name: "Time", type: "value", unit: "s" },
          yAxis: { name: "Velocity", type: "value", unit: "m/s" },
          height: 400,
          showXLine: true,
        }}
      />
      
      <Graph2D
        xData={xDataCircle}
        yData={yDataCircle}
        activeIndex={activeIndexCircle}
        config={{
          title: "Circle Shape Data",
          xAxis: { name: "X", type: "value" },
          yAxis: { name: "Y", type: "value" },
          height: 400,
          showXLine: true,
          showYLine: true,
        }}
      />
    </div>
  );
}
