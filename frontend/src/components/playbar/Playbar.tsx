import React, { useEffect, useState } from 'react';
import styles from './Playbar.module.scss';
import { ReplayController, ReplayEventType, StateType } from '@utils/ReplayController';
import { DiscreteSlider } from '@components/Slider/Slider';
import PlayIcon from '@assets/icons/play.svg?react';
import PauseIcon from '@assets/icons/pause.svg?react';


interface PlaybarProps {
    replayController: ReplayController;
    times: number[];
}

// Be aware that this places the times evenly along the slider, not according to their actual values.
// This is because the slider only supports linear scales. If we want a non-linear scale, we would need to implement a custom slider.
export const Playbar = ({ replayController, times }: PlaybarProps) => {
    // Format seconds to m:ss:ss (minutes:seconds:hundredths). Handles undefined and negatives gracefully.
    const formatTime = (sec?: number) => {
        if (sec == null || !Number.isFinite(sec)) return '-:--:--';
        const clamped = Math.max(0, sec);
        const totalSec = Math.floor(clamped);
        const m = Math.floor(totalSec / 60);
        const s = totalSec % 60;
        const fractional = clamped - totalSec;
        // Hundredths of a second (00-99), avoid rounding to 100
        const hs = Math.floor(Math.min(0.9999, Math.max(0, fractional)) * 100);
        return `${m}:${s.toString().padStart(2, '0')}:${hs.toString().padStart(2, '0')}`;
    };

    const [isPlaying, setIsPlaying] = useState(false);
    const [currentIndex, setCurrentIndex] = useState(0);
    const [speed, setSpeed] = useState(1);

    useEffect(() => {
        const cleanup = replayController.on((event) => {
            if (event.type === ReplayEventType.StateChanged) {
                setIsPlaying(event.state === StateType.Playing);
            } else if (event.type === ReplayEventType.Progress) {
                setCurrentIndex(event.currentIndex);
            } else if (event.type === ReplayEventType.Finished) {
                setIsPlaying(false);
                setCurrentIndex(times.length - 1);
            }
        });
        return cleanup;
    }, [replayController, times.length]);

    const handlePlayPause = () => {
        if (isPlaying) {
            replayController.pause();
        } else {
            replayController.play();
        }
    };

    const speedOptions = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3, 4];
    const handleSpeedChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
        const newSpeed = Number(e.target.value);
        setSpeed(newSpeed);
        replayController.setSpeed(newSpeed);
    };

    const handleSeek = (index: number) => {
        if (isPlaying) {
            replayController.pause();
        }
        setCurrentIndex(index);
        replayController.setCurrentIndex(index);
    };

    return (
        <div className={styles.playbar}>
            <button
                className={styles.playPause}
                onClick={handlePlayPause}
                aria-label={isPlaying ? 'Pause' : 'Play'}
            >
                {isPlaying ? <PauseIcon /> : <PlayIcon />}
            </button>
            <DiscreteSlider
                values={times}
                selectedIndex={currentIndex}
                onIndexChange={handleSeek}
            />
            <span className={styles.indexLabel}>
                {formatTime(times[currentIndex])} / {formatTime(times[times.length - 1])}
            </span>
            <label className={styles.speedLabel}>
                Speed:
                <select
                    value={speed}
                    onChange={handleSpeedChange}
                    className={styles.speedSelect}
                >
                    {speedOptions.map(opt => (
                        <option key={opt} value={opt}>{opt}x</option>
                    ))}
                </select>
            </label>
        </div>
    );
};