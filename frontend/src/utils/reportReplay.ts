export enum ReplayEventType {
  Progress = 'Progress',
  StateChanged = 'StateChanged',
  Finished = 'Finished',
}

export enum StateType {
  Playing = 'Playing',
  Paused = 'Paused',
}

export type ReportReplayEvent =
  | { type: ReplayEventType.Progress; currentIndex: number }
  | { type: ReplayEventType.StateChanged; state: StateType }
  | { type: ReplayEventType.Finished };

export interface VisualReplaySample {
  simulationTime: number;
  lowerIndex: number;
  upperIndex: number;
  alpha: number;
  speed: number;
  playing: boolean;
}

type ReplayHandler = (event: ReportReplayEvent) => void;

/**
 * Timeline-only playback for a flattened CINDER report table.
 *
 * Progress events remain intentionally discrete and row-aligned for graphs,
 * sliders, tables, and exact report consumers. `visualSample()` is a separate,
 * non-emitting presentation surface for animations that need smooth time.
 */
export class ReportReplayController {
  private index = 0;
  private playing = false;
  private speed = 1;
  private startWallClock = 0;
  private startTime = 0;
  private visualTime = 0;
  private pinnedIndex: number | null = 0;
  private rafId: number | null = null;
  private readonly handlers = new Set<ReplayHandler>();

  public constructor(private readonly times: readonly number[]) {
    this.visualTime = this.times[0] ?? 0;
    this.startTime = this.visualTime;
  }

  public on(handler: ReplayHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  public play(): void {
    if (this.times.length < 2) return;
    if (this.index >= this.times.length - 1) this.setCurrentIndex(0);

    this.playing = true;
    this.pinnedIndex = null;
    this.startWallClock = performance.now();
    this.startTime = this.visualTime;
    this.emit({ type: ReplayEventType.StateChanged, state: StateType.Playing });
    this.rafId = requestAnimationFrame(this.step);
  }

  public pause(): void {
    if (!this.playing && this.rafId === null) return;

    if (this.playing) {
      this.visualTime = this.continuousTime(performance.now());
      this.pinnedIndex = null;
    }

    this.playing = false;
    if (this.rafId !== null) cancelAnimationFrame(this.rafId);
    this.rafId = null;
    this.emit({ type: ReplayEventType.StateChanged, state: StateType.Paused });
  }

  public setSpeed(next: number): void {
    if (!Number.isFinite(next) || next <= 0) return;

    if (this.playing) {
      const now = performance.now();
      this.visualTime = this.continuousTime(now);
      this.startTime = this.visualTime;
      this.startWallClock = now;
    }

    this.speed = next;
  }

  public setCurrentIndex(next: number): void {
    const maximum = Math.max(0, this.times.length - 1);
    this.index = Math.max(0, Math.min(maximum, Math.round(next)));
    this.visualTime = this.times[this.index] ?? 0;
    this.startTime = this.visualTime;
    this.pinnedIndex = this.index;

    if (!this.playing) {
      this.emit({ type: ReplayEventType.Progress, currentIndex: this.index });
    }
  }

  /**
   * Smooth, non-emitting playback position for presentation/animation only.
   * Calling this never changes graph/slider/report semantics.
   */
  public visualSample(now = performance.now()): VisualReplaySample {
    if (!this.playing && this.pinnedIndex !== null) {
      return {
        simulationTime: this.times[this.pinnedIndex] ?? this.visualTime,
        lowerIndex: this.pinnedIndex,
        upperIndex: this.pinnedIndex,
        alpha: 0,
        speed: this.speed,
        playing: false,
      };
    }

    const simulationTime = this.playing
      ? this.continuousTime(now)
      : this.visualTime;
    return {
      ...this.sampleAtSimulationTime(simulationTime),
      speed: this.speed,
      playing: this.playing,
    };
  }

  public sampleAtSimulationTime(
    simulationTime: number,
  ): Omit<VisualReplaySample, 'speed' | 'playing'> {
    const count = this.times.length;
    if (count === 0) {
      return { simulationTime: 0, lowerIndex: 0, upperIndex: 0, alpha: 0 };
    }

    const first = this.times[0] ?? 0;
    const last = this.times[count - 1] ?? first;
    const clamped = Math.min(last, Math.max(first, simulationTime));

    if (clamped <= first) {
      return { simulationTime: first, lowerIndex: 0, upperIndex: 0, alpha: 0 };
    }
    if (clamped >= last) {
      const index = count - 1;
      return { simulationTime: last, lowerIndex: index, upperIndex: index, alpha: 0 };
    }

    let low = 0;
    let high = count - 1;
    while (low < high) {
      const mid = Math.ceil((low + high) / 2);
      if ((this.times[mid] ?? Number.POSITIVE_INFINITY) <= clamped) low = mid;
      else high = mid - 1;
    }

    const lowerIndex = low;
    const upperIndex = Math.min(count - 1, lowerIndex + 1);
    const lowerTime = this.times[lowerIndex] ?? clamped;
    const upperTime = this.times[upperIndex] ?? lowerTime;
    const duration = upperTime - lowerTime;
    const alpha = duration > 0
      ? Math.min(1, Math.max(0, (clamped - lowerTime) / duration))
      : 0;

    return { simulationTime: clamped, lowerIndex, upperIndex, alpha };
  }

  public dispose(): void {
    this.pause();
    this.handlers.clear();
  }

  private continuousTime(now: number): number {
    const first = this.times[0] ?? 0;
    const last = this.times[this.times.length - 1] ?? first;
    const target = this.startTime + ((now - this.startWallClock) / 1000) * this.speed;
    return Math.min(last, Math.max(first, target));
  }

  private step = (now: number): void => {
    if (!this.playing) return;

    const targetTime = this.continuousTime(now);
    this.visualTime = targetTime;

    let next = this.index;
    while (
      next < this.times.length - 1
      && (this.times[next + 1] ?? Number.POSITIVE_INFINITY) <= targetTime
    ) {
      next += 1;
    }

    if (next !== this.index) {
      this.index = next;
      this.emit({ type: ReplayEventType.Progress, currentIndex: this.index });
    }

    if (targetTime >= (this.times[this.times.length - 1] ?? targetTime)) {
      this.visualTime = this.times[this.times.length - 1] ?? targetTime;
      this.playing = false;
      this.rafId = null;
      this.emit({ type: ReplayEventType.StateChanged, state: StateType.Paused });
      this.emit({ type: ReplayEventType.Finished });
      return;
    }

    this.rafId = requestAnimationFrame(this.step);
  };

  private emit(event: ReportReplayEvent): void {
    this.handlers.forEach((handler) => handler(event));
  }
}
