// TabsPanel.jsx
import { useState } from 'react';
import '../styling/TabsPanel.css';
import BarChartIcon from '@mui/icons-material/BarChart';
import ArticleIcon from '@mui/icons-material/Article';
import MapIcon from '@mui/icons-material/Map';
import ReverseSearchResults from './ReverseSearchResults';

export function TabsPanel({ analysisResult, gpt_results, captionResult }) {
  const [activeTab, setActiveTab] = useState('overview');

  const tabs = [
    { id: 'overview', label: 'Overview', icon: BarChartIcon },
    { id: 'details', label: 'Caption Check', icon: ArticleIcon },
    { id: 'insights', label: 'Insights', icon: MapIcon }
  ];

  const renderHighlightedCaption = () => {
    if (!captionResult || !captionResult.result) return null;

    const baseCaption =
      (gpt_results &&
        gpt_results.multi_analysis &&
        gpt_results.multi_analysis.caption) ||
      captionResult.result.caption ||
      '';

    const caption = baseCaption;
    const issues = captionResult.result.problematic_phrases || [];

    if (!caption || issues.length === 0) {
      return caption;
    }

    // Build a highlighted version of the caption using problematic phrases
    let nodes = [caption];

    issues.forEach((issue, index) => {
      const phrase = issue.phrase;
      if (!phrase) return;

      const nextNodes = [];

      nodes.forEach((node) => {
        if (typeof node !== 'string') {
          nextNodes.push(node);
          return;
        }

        const parts = node.split(phrase);
        parts.forEach((part, partIndex) => {
          if (part) {
            nextNodes.push(part);
          }
          if (partIndex < parts.length - 1) {
            const type = issue.issue_type || 'misleading';
            nextNodes.push(
              <span
                key={`${index}-${partIndex}-${phrase}`}
                className={`caption-token caption-token--${type}`}
                title={issue.reason}
              >
                {phrase}
              </span>
            );
          }
        });
      });

      nodes = nextNodes;
    });

    return nodes;
  };

  return (
    <div className="tabs-container">
      <div className="tabs-header">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
            >
              <Icon />
              {tab.label}
            </button>
          );
        })}
      </div>

      <div className="tab-content">
        {activeTab === 'overview' && (
          <div className="tab-panel">
            <h3 className="panel-title">Analysis Overview</h3>
            <p className="panel-description">
              {analysisResult
                ? 'Analysis complete! View the results from AIorNot below.'
                : 'Upload an image to see a comprehensive overview of the analysis results.'}
            </p>
            <div className="metrics-grid">
              <div className="metric-card">
                <p className="metric-label">Confidence</p>
                <p className="metric-value">
                  {analysisResult?.report.ai_generated[analysisResult.report.ai_generated.verdict].confidence
                    ? `${(analysisResult.report.ai_generated[analysisResult.report.ai_generated.verdict].confidence * 100).toFixed(1)}%`
                    : '--'}
                </p>
              </div>
              <div className="metric-card">
                <p className="metric-label">Verdict</p>
                <p className="metric-value">
                  {analysisResult?.report.ai_generated.verdict
                    ? `${analysisResult.report.ai_generated.verdict.toUpperCase()}`
                    : '--'}
                </p>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'details' && (
          <div className="tab-panel">
            <h3 className="panel-title">Caption Check</h3>
            <p className="panel-description">
              Compare auto-extracted caption text against what is actually visible in the image.
            </p>

            {captionResult && captionResult.result ? (
              <div className="details-content">
                <div className="assessment-card">
                  <div className="assessment-header">
                    <h4 className="assessment-title">Verdict</h4>
                    <span className={`assessment-badge ${captionResult.result.overall_verdict}`}>
                      {captionResult.result.overall_verdict?.toUpperCase()}
                    </span>
                  </div>

                  <div className="confidence-bar-container">
                    <div className="confidence-label-row">
                      <span className="confidence-label">Alignment confidence</span>
                      <span className="confidence-value">
                        {captionResult.result.alignment_confidence
                          ? `${(captionResult.result.alignment_confidence * 100).toFixed(1)}%`
                          : 'N/A'}
                      </span>
                    </div>
                    {captionResult.result.alignment_confidence && (
                      <div className="confidence-bar">
                        <div
                          className="confidence-fill"
                          style={{ width: `${captionResult.result.alignment_confidence * 100}%` }}
                        ></div>
                      </div>
                    )}
                  </div>
                </div>

                <div className="details-card">
                  <h4 className="section-title">Caption (what the model sees in the image)</h4>
                  <p className="caption-text">
                    {renderHighlightedCaption()}
                  </p>
                  <div className="caption-legend">
                    <span className="caption-legend-item">
                      <span className="caption-legend-swatch caption-token--misleading" /> Misleading / inaccurate
                    </span>
                    <span className="caption-legend-item">
                      <span className="caption-legend-swatch caption-token--exaggeration" /> Exaggerated
                    </span>
                    <span className="caption-legend-item">
                      <span className="caption-legend-swatch caption-token--misinformation" /> Strong misinformation
                    </span>
                  </div>
                </div>

                {captionResult.result.textual_cues && captionResult.result.textual_cues.length > 0 && (
                  <div className="details-card">
                    <h4 className="section-title">Textual cues in the caption</h4>
                    <ul className="textual-cues-list">
                      {captionResult.result.textual_cues.map((cue, index) => (
                        <li key={index} className="textual-cue-item">
                          <span className={`textual-cue-badge textual-cue-${cue.cue_type}`}>
                            {cue.cue_type}
                          </span>
                          <span className="textual-cue-phrase">“{cue.phrase}”</span>
                          <span className="textual-cue-reason">{cue.reason}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {captionResult.result.reasoning_summary && (
                  <div className="details-card">
                    <h4 className="section-title">Explanation</h4>
                    <p className="review-text">
                      {captionResult.result.reasoning_summary}
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <div className="details-card">
                <p className="placeholder-text">
                  Add a caption in the upload panel and run Analyze Image to see the caption check here.
                </p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'insights' && (
          <div className="tab-panel">
            <h3 className="panel-title">AI Detection Analysis</h3>
            <p className="panel-description">
              Structured analysis to detect AI-generated content using GPT-4o.
            </p>

            {gpt_results ? (
              <div className="ai-analysis-section">
                {/* Overall Assessment Card */}
                <div className="assessment-card">
                  <div className="assessment-header">
                    <h4 className="assessment-title">Overall Assessment</h4>
                    <span className={`assessment-badge ${gpt_results.analysis.overall_assessment?.replace(' ', '-')}`}>
                      {gpt_results.analysis.overall_assessment?.toUpperCase() || 'N/A'}
                    </span>
                  </div>
                    <div className="confidence-bar-container">
                    <div className="confidence-label-row">
                      <span className="confidence-label">Confidence Level</span>
                      <span className="confidence-value">
                        {gpt_results.analysis.confidence
                          ? `${(gpt_results.analysis.confidence * 100).toFixed(1)}%`
                          : 'N/A'}
                      </span>
                    </div>
                    {gpt_results.analysis.confidence && (
                      <div className="confidence-bar">
                        <div
                          className="confidence-fill"
                          style={{ width: `${gpt_results.analysis.confidence * 100}%` }}
                        ></div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Artifacts Section */}
                {gpt_results.analysis.artifacts && gpt_results.analysis.artifacts.length > 0 && (
                  <div className="artifacts-section">
                    <h4 className="section-title">Detected Artifacts ({gpt_results.analysis.artifacts.length})</h4>
                    <div className="artifacts-list">
                      {gpt_results.analysis.artifacts.map((artifact, index) => (
                        <div key={index} className="artifact-card">
                          <div className="artifact-header">
                            <div className="artifact-category">
                              <span className="category-badge">{artifact.category}</span>
                              <span className={`severity-badge severity-${artifact.severity}`}>
                                Severity: {artifact.severity}/5
                              </span>
                            </div>
                            <span className={`evidence-badge ${artifact.evidence_strength}`}>
                              {artifact.evidence_strength}
                            </span>
                          </div>

                          <div className="artifact-body">
                            <div className="artifact-row">
                              <span className="artifact-label">Region:</span>
                              <span className="artifact-value">{artifact.region_hint}</span>
                            </div>
                            <div className="artifact-row">
                              <span className="artifact-label">Evidence:</span>
                              <span className="artifact-value">{artifact.evidence}</span>
                            </div>
                            {artifact.benign_alternatives && (
                              <div className="artifact-row">
                                <span className="artifact-label">Alternative:</span>
                                <span className="artifact-value alternative">{artifact.benign_alternatives}</span>
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Quality Controls */}
                {gpt_results.analysis.quality_controls && (
                  <div className="quality-controls-card">
                    <h4 className="section-title">Quality Controls</h4>
                    <div className="quality-content">
                      {gpt_results.analysis.quality_controls.ambiguities && (
                        <div className="quality-item">
                          <span className="quality-label">Ambiguities:</span>
                          <p className="quality-text">{gpt_results.analysis.quality_controls.ambiguities}</p>
                        </div>
                      )}
                      {gpt_results.analysis.quality_controls.assumptions_limited_to_pixels !== undefined && (
                        <div className="quality-item">
                          <span className="quality-label">Pixel-Only Analysis:</span>
                          <span className={`quality-badge ${gpt_results.analysis.quality_controls.assumptions_limited_to_pixels ? 'yes' : 'no'}`}>
                            {gpt_results.analysis.quality_controls.assumptions_limited_to_pixels ? 'Yes' : 'No'}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Human Review Notes */}
                {gpt_results.analysis.notes_for_human_review && (
                  <div className="human-review-card">
                    <h4 className="section-title">Human Review Notes</h4>
                    <p className="review-text">{gpt_results.analysis.notes_for_human_review}</p>
                  </div>
                )}

              </div>
            ) : (
              <div className="insights-card">
                <p className="placeholder-text">
                  Upload and analyze an image to detect AI-generated content
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div >
  );
}