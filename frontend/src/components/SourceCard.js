import React, { useState } from 'react';
import { FileText, ChevronDown, ChevronUp } from 'lucide-react';
import './SourceCard.css';

export default function SourceCard({ source, index }) {
  const [expanded, setExpanded] = useState(false);

  const scorePercent = Math.round(source.score * 100);
  const scoreColor = scorePercent >= 70 ? 'high' : scorePercent >= 40 ? 'medium' : 'low';

  return (
    <div className={`source-card ${expanded ? 'expanded' : ''}`}>
      <button className="source-header" onClick={() => setExpanded(!expanded)}>
        <div className="source-badge">{index}</div>
        <FileText size={12} className="source-file-icon" />
        <div className="source-meta">
          <span className="source-filename">{source.filename}</span>
          <span className="source-page">Page {source.page}</span>
        </div>
        <div className={`score-badge ${scoreColor}`}>{scorePercent}%</div>
        {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>
      {expanded && (
        <div className="source-excerpt">
          <p>{source.excerpt}</p>
        </div>
      )}
    </div>
  );
}
