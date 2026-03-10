import type { RunResponse } from './api';

type DataPoint = RunResponse['data'][number];
type ReplayData = DataPoint[];

export enum ReplayEventType {
  StateChanged = 'stateChanged',
  Progress = 'progress',
  Finished = 'finished',
}

export enum StateType {
  Playing = 'playing',
  Paused = 'paused',
}

type ReplayEvent =
  | { type: ReplayEventType.StateChanged; state: StateType }
  | { type: ReplayEventType.Progress; currentIndex: number; data: DataPoint }
  | { type: ReplayEventType.Finished };

export class ReplayController {
  private data: ReplayData;
  private isPlaying = false;
  private currentIndex = 0;
  private lastTimestamp = 0;
  private startTime = 0;
  private speed = 1;
  private listeners: ((event: ReplayEvent) => void)[] = [];

  // rAF management
  private rafId: number | null = null;
  private loopBound = (now: number) => this.loop(now);

  constructor(
    data: ReplayData,
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
      this.startTime = performance.now() - (this.lastTimestamp * 1000) / this.speed; // Convert seconds to ms
    }

    this.emit({ type: ReplayEventType.StateChanged, state: StateType.Playing });
    this.isPlaying = true;

    // ensure only one rAF loop
    if (this.rafId != null) cancelAnimationFrame(this.rafId);
    this.rafId = requestAnimationFrame(this.loopBound);
  }

  pause() {
    this.isPlaying = false;
    if (this.rafId != null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    this.emit({ type: ReplayEventType.StateChanged, state: StateType.Paused });
  }

  reset() {
    this.currentIndex = 0;
    this.lastTimestamp = 0;
  }

  setSpeed(newSpeed: number) {
    if (newSpeed <= 0) {
      alert('Speed must be positive. Invalid value ignored.');
      return;
    }
    // keep timeline continuous when changing speed during playback
    if (this.isPlaying) {
      const now = performance.now();
      const elapsedSec = ((now - this.startTime) / 1000) * this.speed;
      this.startTime = now - (elapsedSec * 1000) / newSpeed;
    }
    this.speed = newSpeed;
  }

  // Get the first data point without starting playback
  getFirstDataPoint(): DataPoint | null {
    return this.data.length > 0 ? this.data[0] : null;
  }

  // Set the current index and update lastTimestamp accordingly
  setCurrentIndex(idx: number) {
    if (idx < 0 || idx >= this.data.length) return;
    this.currentIndex = idx;
    this.lastTimestamp = this.data[idx]?.time || 0;
    // Emit progress event if paused
    if (!this.isPlaying) {
      this.emit({
        type: ReplayEventType.Progress,
        currentIndex: idx,
        data: this.data[idx],
      });
    }
  }

   /** Advance indices up to the given elapsed time.
   * Returns the latest DataPoint processed in this frame (or null). */
  private stepUntil(elapsedSeconds: number): DataPoint | null {
    let lastPoint: DataPoint | null = null;

    while (
      this.currentIndex < this.data.length &&
      this.data[this.currentIndex].time <= elapsedSeconds
    ) {
      lastPoint = this.data[this.currentIndex];
      this.lastTimestamp = lastPoint.time;
      this.currentIndex++;
    }

    return lastPoint;
  }

  /** Single rAF callback that:
   *  - computes elapsed,
   *  - advances simulation (possibly multiple data points),
   *  - emits at most once with the latest point,
   *  - schedules the next frame. */
  private loop(now: number) {
    if (!this.isPlaying) return;

    const elapsedSec = ((now - this.startTime) / 1000) * this.speed;
    const latest = this.stepUntil(elapsedSec);

    if (latest) {
      this.emit({
        type: ReplayEventType.Progress,
        currentIndex: this.currentIndex,
        data: latest, // only the newest point this frame
      });
    }

    if (this.currentIndex >= this.data.length) {
      this.pause();
      this.emit({ type: ReplayEventType.Finished });
      return;
    }

    this.rafId = requestAnimationFrame(this.loopBound);
  }
}