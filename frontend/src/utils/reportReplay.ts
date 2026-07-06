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

type ReplayHandler = (event: ReportReplayEvent) => void;

/**
 * Timeline-only playback for a flattened CINDER report table. Unlike the old
 * replay helper, this object owns no nested simulation data or CVT accessors.
 */
export class ReportReplayController {
  private index = 0;
  private playing = false;
  private speed = 1;
  private startWallClock = 0;
  private startTime = 0;
  private rafId: number | null = null;
  private readonly handlers = new Set<ReplayHandler>();

  public constructor(private readonly times: readonly number[]) {}

  public on(handler: ReplayHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  public play(): void {
    if (this.times.length < 2) return;
    if (this.index >= this.times.length - 1) this.setCurrentIndex(0);
    this.playing = true;
    this.startWallClock = performance.now();
    this.startTime = this.times[this.index] ?? 0;
    this.emit({ type: ReplayEventType.StateChanged, state: StateType.Playing });
    this.rafId = requestAnimationFrame(this.step);
  }

  public pause(): void {
    if (!this.playing && this.rafId === null) return;
    this.playing = false;
    if (this.rafId !== null) cancelAnimationFrame(this.rafId);
    this.rafId = null;
    this.emit({ type: ReplayEventType.StateChanged, state: StateType.Paused });
  }

  public setSpeed(next: number): void {
    if (Number.isFinite(next) && next > 0) this.speed = next;
  }

  public setCurrentIndex(next: number): void {
    const maximum = Math.max(0, this.times.length - 1);
    this.index = Math.max(0, Math.min(maximum, Math.round(next)));
    this.startTime = this.times[this.index] ?? 0;
    if (!this.playing) this.emit({ type: ReplayEventType.Progress, currentIndex: this.index });
  }

  public dispose(): void { this.pause(); this.handlers.clear(); }

  private step = (now: number): void => {
    if (!this.playing) return;
    const targetTime = this.startTime + ((now - this.startWallClock) / 1000) * this.speed;
    let next = this.index;
    while (next < this.times.length - 1 && (this.times[next + 1] ?? Infinity) <= targetTime) next += 1;
    if (next !== this.index) {
      this.index = next;
      this.emit({ type: ReplayEventType.Progress, currentIndex: this.index });
    }
    if (this.index >= this.times.length - 1) {
      this.pause();
      this.emit({ type: ReplayEventType.Finished });
      return;
    }
    this.rafId = requestAnimationFrame(this.step);
  };

  private emit(event: ReportReplayEvent): void { this.handlers.forEach((handler) => handler(event)); }
}
