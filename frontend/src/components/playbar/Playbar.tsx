import React, { useEffect, useState } from 'react';
import styles from './Playbar.module.scss';
import { ReplayController, ReplayEventType, StateType } from '@utils/ReplayController';
import Slider from '@mui/material/Slider';
import PlayIcon from '@assets/icons/play.svg?react';
import PauseIcon from '@assets/icons/pause.svg?react';


interface PlaybarProps {
    replayController: ReplayController;
    times: number[];
}

// Be aware that this places the times evenly along the slider, not according to their actual values.
// This is because the slider only supports linear scales. If we want a non-linear scale, we would need to implement a custom slider.
export const Playbar: React.FC<PlaybarProps> = ({ replayController, times }) => {
    const [isPlaying, setIsPlaying] = useState(false);
    const [currentIndex, setCurrentIndex] = useState(0);
    const [speed, setSpeed] = useState(1);
    const [dragging, setDragging] = useState(false);

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

    const handleSeek = (_: Event | React.SyntheticEvent, idx: number | number[]) => {
        const index = Array.isArray(idx) ? idx[0] : idx;
        setCurrentIndex(index);
        replayController.setCurrentIndex(index);
    };

    const handleDragStart = () => setDragging(true);
    const handleDragEnd = () => setDragging(false);

    return (
        <div className={styles.playbar}>
            <button
                className={styles.playPause}
                onClick={handlePlayPause}
                aria-label={isPlaying ? 'Pause' : 'Play'}
            >
                {isPlaying ? <PauseIcon /> : <PlayIcon />}
            </button>
            <Slider
                min={0}
                max={times.length - 1}
                step={1}
                value={currentIndex}
                onChange={handleSeek}
                onMouseDown={handleDragStart}
                onMouseUp={handleDragEnd}
                onTouchStart={handleDragStart}
                onTouchEnd={handleDragEnd}
                marks={times.length > 0 ? [
                    { value: 0, label: `${times[0]}` },
                    { value: times.length - 1, label: `${times[times.length - 1]}` }
                ] : []}
                className={dragging ? `${styles.slider} ${styles.dragging}` : styles.slider} // TODO: Add dragging styles + use cx
                sx={{ flex: 1, mx: 2 }}
            />
            <span className={styles.indexLabel}>
                {currentIndex + 1} / {times.length} ({times[currentIndex] ?? '-'})
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