import { useState } from 'react';
import ImageUpload from './components/ImageUpload';
import { TabsPanel } from './components/TabsPanel';
import './index.css';

export default function App() {
  const [uploadedImage, setUploadedImage] = useState(null);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [gptResult, setGPTResult] = useState(null);
  const [captionCheckResult, setCaptionCheckResult] = useState(null);

  const handleImageUpload = (image) => {
    setUploadedImage(image);
    // Clear previous results when new image is uploaded
    setAnalysisResult(null);
    setGPTResult(null);
    setCaptionCheckResult(null);
  };

  const handleAnalysisComplete = (result, gpt_result, caption_result) => {
    setAnalysisResult(result);
    setGPTResult(gpt_result);
    if (caption_result) {
      setCaptionCheckResult(caption_result);
    } else {
      setCaptionCheckResult(null);
    }
  };

  return (
    <div className="app-container">
      <div className="app-content">
        <h1 className="app-title">Image Analysis Dashboard</h1>

        <div className="dashboard-grid">
          <div className="upload-section">
            <ImageUpload
              onImageUpload={handleImageUpload}
              onAnalysisComplete={handleAnalysisComplete}
            />
          </div>

          <div className="tabs-section">
            <TabsPanel
              analysisResult={analysisResult}
              gpt_results={gptResult}
              captionResult={captionCheckResult}
            />
          </div>
        </div>
      </div>
    </div>
  );
}