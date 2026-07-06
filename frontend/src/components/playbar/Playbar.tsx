import React, { useCallback, useEffect, useRef, useState } from 'react';
import styles from './Playbar.module.scss';
import { ReportReplayController, ReplayEventType, StateType } from '@utils/reportReplay';
import { DiscreteSlider } from '@components/Slider/Slider';
import { SpeedSelector } from '@components/SpeedSelector/SpeedSelector';
import PlayIcon from '@assets/icons/play.svg?react';
import PauseIcon from '@assets/icons/pause.svg?react';

interface PlaybarProps {
  replayController: ReportReplayController;
  times: number[];
}

// Keep this outside so it isn't recreated every render
function formatTime(sec?: number) {
  if (sec == null || !Number.isFinite(sec)) return '-:--:--';
  const clamped = Math.max(0, sec);
  const totalSec = Math.floor(clamped);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  const fractional = clamped - totalSec;
  const hs = Math.floor(Math.min(0.9999, Math.max(0, fractional)) * 100);
  return `${m}:${s.toString().padStart(2, '0')}:${hs.toString().padStart(2, '0')}`;
}

/** Memo'd pieces **/

const PlayPauseButton = React.memo(function PlayPauseButton({
  isPlaying,
  onToggle,
}: {
  isPlaying: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      className={styles.playPause}
      onClick={onToggle}
      aria-label={isPlaying ? 'Pause' : 'Play'}
    >
      {isPlaying ? <PauseIcon /> : <PlayIcon />}
    </button>
  );
});

const TimeLabel = React.memo(function TimeLabel({
  currentTime,
  endTime,
}: {
  currentTime: number | undefined;
  endTime: number | undefined;
}) {
  return (
    <span className={styles.indexLabel}>
      {formatTime(currentTime)} / {formatTime(endTime)}
    </span>
  );
});

const SeekSlider = React.memo(function SeekSlider({
  times,
  selectedIndex,
  onSeek,
}: {
  times: number[];
  selectedIndex: number;
  onSeek: (idx: number) => void;
}) {
  return <DiscreteSlider values={times} selectedIndex={selectedIndex} onIndexChange={onSeek} />;
});

const SpeedControl = React.memo(function SpeedControl({
  speed,
  onSpeedChange,
}: {
  speed: number;
  onSpeedChange: (s: number) => void;
}) {
  return <SpeedSelector speed={speed} onSpeedChange={onSpeedChange} />;
});

export const Playbar = ({ replayController, times }: PlaybarProps) => {
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);

  // UI index: only for display/slider
  const [uiIndex, setUiIndex] = useState(0);

  // Refs so callbacks can be stable and not depend on changing state
  const isPlayingRef = useRef(isPlaying);
  useEffect(() => {
    isPlayingRef.current = isPlaying;
  }, [isPlaying]);

  useEffect(() => {
    return replayController.on((event) => {
      if (event.type === ReplayEventType.StateChanged) {
        setIsPlaying(event.state === StateType.Playing);
        return;
      }

      if (event.type === ReplayEventType.Progress) {
        setUiIndex(event.currentIndex);
        return;
      }

      if (event.type === ReplayEventType.Finished) {
        setIsPlaying(false);
        setUiIndex(Math.max(0, times.length - 1));
      }
    });
  }, [replayController, times.length]);

  // Stable toggle handler (doesn't change identity when isPlaying changes)
  const handlePlayPause = useCallback(() => {
    if (isPlayingRef.current) replayController.pause();
    else replayController.play();
  }, [replayController]);

  // Spacebar listener attaches once (because handlePlayPause is stable)
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.code === 'Space') {
        event.preventDefault();
        handlePlayPause();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [handlePlayPause]);

  const handleSpeedChange = useCallback(
    (newSpeed: number) => {
      setSpeed(newSpeed);
      replayController.setSpeed(newSpeed);
    },
    [replayController]
  );

  const handleSeek = useCallback(
    (index: number) => {
      // If user scrubs while playing, pause first
      if (isPlayingRef.current) replayController.pause();

      setUiIndex(index);
      replayController.setCurrentIndex(index);
    },
    [replayController]
  );

  const currentTime = times[uiIndex];
  const endTime = times[times.length - 1];

  return (
    <div className={styles.playbar}>
      <PlayPauseButton isPlaying={isPlaying} onToggle={handlePlayPause} />
      <TimeLabel currentTime={currentTime} endTime={endTime} />
      <SeekSlider times={times} selectedIndex={uiIndex} onSeek={handleSeek} />
      <SpeedControl speed={speed} onSpeedChange={handleSpeedChange} />
    </div>
  );
};
