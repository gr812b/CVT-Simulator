


import React, { useEffect, useState } from 'react';
import styles from './Playbar.module.scss';
import { ModelReplayController, ReplayEventType, StateType } from '@utils/ReplayController';
import Slider from '@mui/material/Slider';


interface PlaybarProps {
    replayController: ModelReplayController;
    times: number[];
}


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

    const handleSpeedChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const newSpeed = Number(e.target.value);
        setSpeed(newSpeed);
        replayController.setSpeed(newSpeed);
    };

    const handleSeek = (_: any, idx: number | number[]) => {
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
                {isPlaying ? '⏸' : '▶️'}
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
                <input
                    type="number"
                    min={0.1}
                    max={10}
                    step={0.25}
                    value={speed}
                    onChange={handleSpeedChange}
                    className={styles.speedInput}
                />
                x
            </label>
        </div>
    );
};