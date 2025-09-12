// TODO: Align this with the actual data we expect from the api
interface dataPoint {
    timestamp: number;
    rpm: number;
    car_speed: number;
}

type replayData = dataPoint[];

enum ReplayEventType {
  StateChanged = 'stateChanged',
  Progress = 'progress',
  Finished = 'finished',
}

enum StateType {
  Playing = 'playing',
  Paused = 'paused',
}

type ReplayEvent =
  | { type: ReplayEventType.StateChanged; state: StateType }
  | { type: ReplayEventType.Progress; currentIndex: number; data: dataPoint }
  | { type: ReplayEventType.Finished };

export class ModelReplayController {
  private data: replayData;
  private isPlaying = false;
  private currentIndex = 0;
  private lastTimestamp = 0;
  private startTime = 0;
  private speed = 1;
  private listeners: ((event: ReplayEvent) => void)[] = [];

  constructor(
    data: replayData,
  ) {
    this.data = data;
  }

  // Here we setup event listeners to allow other components to listen in on the state of the replaying

  // This allows users to subscribe to events
  on(eventHandler: (event: ReplayEvent) => void) {
    this.listeners.push(eventHandler);
    // Return a cleanup function to unsubscribe
    return () => {
      this.off(eventHandler);
    };
  }

  // This allows users to unsubscribe from events
  off(eventHandler: (event: ReplayEvent) => void) {
    this.listeners = this.listeners.filter((handler) => handler !== eventHandler);
  }

  // This allows us to update listeners with an event
  private emit(event: ReplayEvent) {
    this.listeners.forEach((handler) => handler(event));
  }

  // Below is the state machine functionality for the replaying
  play() {
    if (this.isPlaying) return;

    // Initialize start time if playing from the beginning
    if (this.currentIndex === 0) {
      this.startTime = performance.now();
    } else if (this.currentIndex >= this.data.length) {
      this.reset();
      this.startTime = performance.now();
    } else {
      // Adjust the start time for resuming from the current index
      this.startTime = performance.now() - this.lastTimestamp / this.speed;
    }

    this.emit({ type: ReplayEventType.StateChanged, state: StateType.Playing });
    this.isPlaying = true;

    this.loop();
  }

  pause() {
    this.isPlaying = false;
    this.emit({ type: ReplayEventType.StateChanged, state: StateType.Paused });
  }

  reset() {
    this.currentIndex = 0;
    this.lastTimestamp = 0;
  }

  setSpeed(newSpeed: number) {
    if (newSpeed <= 0) {
      // TODO: Remove debugging statement
      // eslint-disable-next-line no-console
      console.warn('Speed must be positive. Ignoring invalid value:', newSpeed);
      return;
    }
    this.speed = newSpeed;
  }

  private loop() {
    if (!this.isPlaying) return;

    const now = performance.now();
    const elapsed = (now - this.startTime) * this.speed;

    while (
      this.currentIndex < this.data.length &&
      this.data[this.currentIndex].timestamp <= elapsed
    ) {
      const dataPoint = this.data[this.currentIndex];

      this.emit({
        type: ReplayEventType.Progress,
        currentIndex: this.currentIndex,
        data: dataPoint,
      });

      this.lastTimestamp = dataPoint.timestamp;
      this.currentIndex++;
    }

    if (this.currentIndex >= this.data.length) {
      this.pause();
      this.emit({ type: ReplayEventType.Finished });
      return;
    }

    // Continue the loop
    requestAnimationFrame(this.loop.bind(this));
  }
}