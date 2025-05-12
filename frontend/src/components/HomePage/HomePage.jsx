// frontend/src/components/HomePage/HomePage.jsx
import React from 'react';
import styles from './HomePage.module.css';

// Added navigateToYouTubeDiarization prop
function HomePage({ navigateToDiarization, navigateToYouTubeDiarization }) {
  return (
    <div className={styles.homeContainer}>
      <div className={styles.heroSection}>
        <h1 className={styles.title}>Welcome to the Speaker Diarization Tool</h1>
        <p className={styles.subtitle}>
          Easily transcribe and identify speakers in your audio files from various sources.
        </p>
        <div className={styles.ctaButtonsContainer}>
          <button onClick={navigateToDiarization} className={`${styles.ctaButton} ${styles.ctaButtonPrimary}`}>
            Diarize .WAV File
          </button>
          <button onClick={navigateToYouTubeDiarization} className={`${styles.ctaButton} ${styles.ctaButtonSecondary}`}>
            Diarize YouTube Video
          </button>
        </div>
      </div>

      <div className={styles.featuresSection}>
        <h2 className={styles.sectionTitle}>Features</h2>
        <div className={styles.featuresGrid}>
          <div className={styles.featureCard}>
            <span className={styles.featureIcon}>🎤</span>
            <h3>Upload & Process .WAV</h3>
            <p>Supports direct .wav file uploads for quick processing.</p>
          </div>
          <div className={styles.featureCard}>
            <span className={styles.featureIcon}>▶️</span>
            <h3>YouTube Integration</h3>
            <p>Extract and process audio directly from YouTube links.</p>
          </div>
          <div className={styles.featureCard}>
            <span className={styles.featureIcon}>👥</span>
            <h3>Speaker Identification</h3>
            <p>Automatically identifies different speakers in the audio.</p>
          </div>
          <div className={styles.featureCard}>
            <span className={styles.featureIcon}>✏️</span>
            <h3>Edit Transcript</h3>
            <p>Manually correct speaker labels and transcript text.</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default HomePage;
