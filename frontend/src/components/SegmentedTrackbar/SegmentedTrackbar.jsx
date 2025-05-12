// frontend/src/components/YouTubeDiarizationPage/SegmentedTrackbar.jsx
import React, { useState, useEffect, useRef } from 'react';
import styles from './SegmentedTrackbar.module.css';

// Helper to generate distinct colors for speakers
const getSpeakerColor = (speakerId, index) => {
  const colors = [
    '#3498db', '#e74c3c', '#2ecc71', '#f1c40f', '#9b59b6',
    '#1abc9c', '#d35400', '#34495e', '#7f8c8d', '#27ae60'
  ];
  // Simple hash function for more colors if needed, or use index
  if (typeof speakerId === 'string') {
    let hash = 0;
    for (let i = 0; i < speakerId.length; i++) {
      hash = speakerId.charCodeAt(i) + ((hash << 5) - hash);
    }
    return colors[Math.abs(hash) % colors.length];
  }
  return colors[index % colors.length];
};

function SegmentedTrackbar({ segments, duration, onSeek, videoElement }) {
  const trackbarRef = useRef(null);
  const [currentTime, setCurrentTime] = useState(0);

  useEffect(() => {
    const video = videoElement; // Directly use the passed video element ref's current value
    if (video) {
      const handleTimeUpdate = () => {
        setCurrentTime(video.currentTime);
      };
      video.addEventListener('timeupdate', handleTimeUpdate);
      return () => {
        video.removeEventListener('timeupdate', handleTimeUpdate);
      };
    }
  }, [videoElement]);


  const handleTrackbarClick = (event) => {
    if (trackbarRef.current && duration > 0) {
      const rect = trackbarRef.current.getBoundingClientRect();
      const clickX = event.clientX - rect.left;
      const percentage = clickX / rect.width;
      const seekTime = percentage * duration;
      onSeek(seekTime);
    }
  };

  if (!segments || duration <= 0) {
    return null; // Don't render if no data or duration
  }

  return (
    <div className={styles.trackbarContainer} ref={trackbarRef} onClick={handleTrackbarClick}>
      <div className={styles.trackbarBackground}>
        {segments.map((segment, index) => {
          const leftPercent = (segment.start_time / duration) * 100;
          const widthPercent = ((segment.end_time - segment.start_time) / duration) * 100;
          const color = getSpeakerColor(segment.speaker, index);

          return (
            <div
              key={segment.id || `segment-${index}`}
              className={styles.segmentBlock}
              title={`${segment.speaker}: ${segment.text.substring(0,50)}...`}
              style={{
                left: `${leftPercent}%`,
                width: `${Math.max(0.1, widthPercent)}%`, // Ensure a minimum visible width
                backgroundColor: color,
              }}
            />
          );
        })}
        {/* Current time indicator */}
        <div 
          className={styles.currentTimeIndicator} 
          style={{ left: `${(currentTime / duration) * 100}%` }}
        />
      </div>
    </div>
  );
}

export default SegmentedTrackbar;
