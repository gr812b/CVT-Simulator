# Streaming API Usage

The simulation now supports streaming progress updates to prevent timeouts and provide real-time feedback.

## Backend

### Endpoint: `POST /run/stream`

Returns newline-delimited JSON (NDJSON) with streaming progress updates:

**Response Stream Messages:**
- Progress: `{"type": "progress", "percent": 12.5}`
- Complete: `{"type": "complete", "data": {...}}`
- Error: `{"type": "error", "message": "..."}`

### Original Endpoint: `POST /run`

The original `/run` endpoint still works for backwards compatibility, but may timeout on long simulations.

## Frontend

### Using the Streaming API

```typescript
import { runSimulationStreaming } from '@/utils/api';

// Basic usage with progress callback
const result = await runSimulationStreaming(
  { flyweight_mass: 0.4 },
  (percent) => {
    console.log(`Progress: ${percent}%`);
  }
);

// Usage with React state
const [progress, setProgress] = useState(0);
const [isRunning, setIsRunning] = useState(false);

const handleRun = async () => {
  setIsRunning(true);
  setProgress(0);
  
  try {
    const result = await runSimulationStreaming(
      simulationParams,
      (percent) => setProgress(percent)
    );
    // Handle result
    console.log('Simulation complete:', result);
  } catch (error) {
    console.error('Simulation failed:', error);
  } finally {
    setIsRunning(false);
  }
};

// In JSX:
{isRunning && (
  <div>
    <progress value={progress} max={100} />
    <span>{progress.toFixed(1)}%</span>
  </div>
)}
```

### Using the Original Non-Streaming API

```typescript
import { runSimulation } from '@/utils/api';

// Simple request-response (may timeout on long runs)
const result = await runSimulation({ flyweight_mass: 0.4 });
```

## How It Works

1. **Backend Progress Tracking**: The simulation calls a progress callback during ODE solving
2. **NDJSON Streaming**: Progress updates are streamed as newline-delimited JSON
3. **Frontend Parsing**: The fetch API reads the stream and parses each line
4. **Real-time Updates**: Progress callbacks fire as data arrives
5. **Keep-Alive**: Regular updates prevent timeout disconnection

## Benefits

- ✅ **No Timeouts**: Connection stays alive with regular progress updates
- ✅ **Real-time Feedback**: Users see progress as simulation runs
- ✅ **Better UX**: Visual progress bars instead of waiting blindly
- ✅ **Error Handling**: Errors are streamed immediately, not after timeout
- ✅ **Backwards Compatible**: Original `/run` endpoint still works
