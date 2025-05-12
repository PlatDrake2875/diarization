// frontend/src/components/TranscriptEditor/TranscriptEditor.jsx
import React, { useState, useEffect } from 'react';
import styles from './TranscriptEditor.module.css';

function TranscriptEditor({ initialTranscript, onTranscriptChange, fileName }) {
  const [segments, setSegments] = useState([]);

  useEffect(() => {
    // Create a deep copy and ensure each segment has a unique ID for React keys
    // This also helps in preventing direct mutation of props.
    setSegments(
      initialTranscript.map((seg, index) => ({
        ...seg,
        // Use a more robust unique ID if backend provides one, otherwise generate
        id: seg.id || `seg-${index}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      }))
    );
  }, [initialTranscript]);

  const handleSpeakerChange = (id, newSpeaker) => {
    const updatedSegments = segments.map(seg =>
      seg.id === id ? { ...seg, speaker: newSpeaker } : seg
    );
    setSegments(updatedSegments);
    onTranscriptChange(updatedSegments); // Notify App component of the change
  };

  const handleTextChange = (id, newText) => {
    const updatedSegments = segments.map(seg =>
      seg.id === id ? { ...seg, text: newText } : seg
    );
    setSegments(updatedSegments);
    onTranscriptChange(updatedSegments); // Notify App component
  };

  const formatTime = (seconds) => {
    if (typeof seconds !== 'number' || isNaN(seconds)) {
      return "00:00.000";
    }
    const minutes = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    const millis = Math.floor((seconds - Math.floor(seconds)) * 1000);
    return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${String(millis).padStart(3, '0')}`;
  };

  const downloadTranscript = () => {
    const content = segments.map(seg => 
      `[${seg.speaker}] (${formatTime(seg.start_time)}s - ${formatTime(seg.end_time)}s): ${seg.text}`
    ).join('\n');
    
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    
    // Create a filename for download
    const baseFileName = fileName ? fileName.substring(0, fileName.lastIndexOf('.')) || fileName : 'transcript';
    link.download = `${baseFileName}_edited.txt`;
    
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  if (!segments || segments.length === 0) {
    return <p className={styles.noDataMessage}>No transcript data to display or edit.</p>;
  }

  return (
    <div className={styles.editorContainer}>
      <div className={styles.editorHeader}>
        <h2 className={styles.title}>Edit Transcript: <span className={styles.fileName}>{fileName}</span></h2>
        <button onClick={downloadTranscript} className={styles.downloadButton}>
          Download Edited Transcript
        </button>
      </div>
      
      <div className={styles.transcriptGrid}>
        {segments.map((segment) => (
          <div key={segment.id} className={styles.segment}>
            <div className={styles.segmentMeta}>
              <input
                type="text"
                value={segment.speaker}
                onChange={(e) => handleSpeakerChange(segment.id, e.target.value)}
                className={styles.speakerInput}
                placeholder="Speaker ID"
              />
              <span className={styles.timestamp}>
                {formatTime(segment.start_time)} - {formatTime(segment.end_time)}
              </span>
            </div>
            <textarea
              value={segment.text}
              onChange={(e) => handleTextChange(segment.id, e.target.value)}
              className={styles.textInput}
              rows={3} // Adjust as needed
              placeholder="Segment text..."
            />
          </div>
        ))}
      </div>
    </div>
  );
}

export default TranscriptEditor;
