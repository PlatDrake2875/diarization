// frontend/src/components/FileUpload/FileUpload.jsx
import React, { useState, useRef } from 'react';
import axios from 'axios';
import styles from './FileUpload.module.css';

// Added onProcessingStart prop
function FileUpload({ onUploadSuccess, onUploadError, onProcessingStart }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileNameDisplay, setFileNameDisplay] = useState('No file chosen');
  const fileInputRef = useRef(null);

  const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (file) {
      if (file.name.endsWith('.wav')) {
        setSelectedFile(file);
        setFileNameDisplay(file.name);
        if (onUploadError) onUploadError(''); // Clear previous errors if callback exists
      } else {
        setSelectedFile(null);
        setFileNameDisplay('Invalid file type (WAV only)');
        if (onUploadError) onUploadError("Invalid file type. Please upload a .wav file.");
      }
    } else {
      setSelectedFile(null);
      setFileNameDisplay('No file chosen');
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      if (onUploadError) onUploadError("Please select a .wav file first.");
      return;
    }

    if (onProcessingStart) onProcessingStart(); // Signal that processing is starting

    const formData = new FormData();
    formData.append('audio_file', selectedFile);

    try {
      const response = await axios.post('http://localhost:5000/api/diarize', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      if (onUploadSuccess) onUploadSuccess(response.data.transcript, selectedFile.name);
    } catch (err) {
      console.error("Upload error details:", err);
      let errorMessage = "Diarization failed. ";
      if (err.response) {
        errorMessage += `Server responded with ${err.response.status}: ${err.response.data?.error || 'Unknown server error.'}`;
      } else if (err.request) {
        errorMessage += "No response from server. Is the backend running and accessible?";
      } else {
        errorMessage += `Request setup error: ${err.message}`;
      }
      if (onUploadError) onUploadError(errorMessage);
    }
    // setIsLoading is now handled by onProcessingStart, onUploadSuccess, onUploadError in App.jsx
  };
  
  const triggerFileSelect = () => {
    fileInputRef.current.click();
  };

  return (
    <div className={styles.uploadSection}>
      <h2 className={styles.title}>Upload Audio File</h2>
      <p className={styles.instructions}>Select a `.wav` audio file to begin diarization.</p>
      
      <input 
        type="file" 
        accept=".wav" 
        onChange={handleFileChange} 
        className={styles.hiddenFileInput}
        ref={fileInputRef} 
        id="audioFileUpload"
      />

      <button type="button" onClick={triggerFileSelect} className={styles.chooseFileButton}>
        Choose .wav File
      </button>
      <span className={styles.fileNameDisplay}>{fileNameDisplay}</span>

      {selectedFile && (
        <button onClick={handleUpload} className={styles.uploadButton}>
          Upload and Diarize
        </button>
      )}
    </div>
  );
}

export default FileUpload;
