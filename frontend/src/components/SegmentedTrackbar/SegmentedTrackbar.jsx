// frontend/src/components/YouTubeDiarizationPage/SegmentedTrackbar.jsx
import React, { useState, useEffect, useRef, useMemo } from 'react';
import styles from './SegmentedTrackbar.module.css';

// Helper to generate distinct colors for speakers
const getSpeakerColor = (speakerId, speakerIndex) => {
  const colors = [
    '#3498db', '#e74c3c', '#2ecc71', '#f1c40f', '#9b59b6',
    '#1abc9c', '#d35400', '#34495e', '#7f8c8d', '#27ae60',
    '#e67e22', '#16a085', '#c0392b', '#8e44ad', '#2980b9'
  ];
  if (typeof speakerId === 'string') {
    let hash = 0;
    for (let i = 0; i < speakerId.length; i++) {
      hash = speakerId.charCodeAt(i) + ((hash << 5) - hash);
      hash = hash & hash; // Convert to 32bit integer
    }
    return colors[Math.abs(hash) % colors.length];
  }
  return colors[speakerIndex % colors.length];
};

function SegmentedTrackbar({ segments, duration, onSeek, videoElement }) {
  const trackbarContainerRef = useRef(null);
  const [currentTime, setCurrentTime] = useState(0);

  useEffect(() => {
    const video = videoElement; 
    if (video) {
      const handleTimeUpdate = () => {
        setCurrentTime(video.currentTime);
      };
      const handleLoadedMetadata = () => { // Ensure currentTime is updated if video reloads
        setCurrentTime(video.currentTime);
      };
      video.addEventListener('timeupdate', handleTimeUpdate);
      video.addEventListener('loadedmetadata', handleLoadedMetadata); // For initial load/reload
      setCurrentTime(video.currentTime); // Set initial time
      return () => {
        video.removeEventListener('timeupdate', handleTimeUpdate);
        video.removeEventListener('loadedmetadata', handleLoadedMetadata);
      };
    }
  }, [videoElement]);

  const handleTrackbarClick = (event) => {
    if (trackbarContainerRef.current && duration > 0) {
      const rect = trackbarContainerRef.current.getBoundingClientRect();
      const clickX = event.clientX - rect.left;
      const percentage = clickX / rect.width;
      const seekTime = percentage * duration;
      onSeek(seekTime);
    }
  };

  // Group segments by speaker
  const segmentsBySpeaker = useMemo(() => {
    if (!segments) return {};
    return segments.reduce((acc, segment) => {
      const speaker = segment.speaker || 'UNKNOWN_SPEAKER';
      if (!acc[speaker]) {
        acc[speaker] = [];
      }
      acc[speaker].push(segment);
      return acc;
    }, {});
  }, [segments]);

  const speakerOrder = useMemo(() => Object.keys(segmentsBySpeaker), [segmentsBySpeaker]);

  if (!segments || segments.length === 0 || duration <= 0) {
    return <div className={styles.trackbarPlaceholder}>No diarization data to display on trackbar.</div>;
  }

  return (
    <div 
      className={styles.trackbarContainer} 
      ref={trackbarContainerRef} 
      onClick={handleTrackbarClick}
      role="slider"
      aria-valuemin="0"
      aria-valuemax={duration}
      aria-valuenow={currentTime}
      aria-label="Video progress with speaker segments"
      tabIndex={0} // Make it focusable
      onKeyDown={(e) => { // Basic keyboard navigation
        if (e.key === 'ArrowLeft') onSeek(Math.max(0, currentTime - 5));
        if (e.key === 'ArrowRight') onSeek(Math.min(duration, currentTime + 5));
      }}
    >
      {speakerOrder.map((speakerId, speakerIndex) => (
        <div key={speakerId} className={styles.speakerRowTrack}>
          <div className={styles.speakerLabel} style={{ backgroundColor: getSpeakerColor(speakerId, speakerIndex) }}>
            {speakerId}
          </div>
          <div className={styles.trackbarBackground}>
            {(segmentsBySpeaker[speakerId] || []).map((segment, segmentIndex) => {
              const leftPercent = (segment.start_time / duration) * 100;
              const widthPercent = ((segment.end_time - segment.start_time) / duration) * 100;
              
              return (
                <div
                  key={segment.id || `segment-${speakerId}-${segmentIndex}`}
                  className={styles.segmentBlock}
                  title={`${speakerId} (${segment.start_time.toFixed(2)}s - ${segment.end_time.toFixed(2)}s): ${segment.text.substring(0, 50)}...`}
                  style={{
                    left: `${leftPercent}%`,
                    width: `${Math.max(0.2, widthPercent)}%`, // Ensure a minimum visible width
                    backgroundColor: getSpeakerColor(speakerId, speakerIndex),
                  }}
                />
              );
            })}
          </div>
        </div>
      ))}
      {/* Current time indicator - spans all rows */}
      <div 
        className={styles.currentTimeIndicator} 
        style={{ left: `${(currentTime / duration) * 100}%` }}
        aria-hidden="true"
      />
    </div>
  );
}

export default SegmentedTrackbar;
