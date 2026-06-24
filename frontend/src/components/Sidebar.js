import React, { useCallback, useRef } from 'react';
import { Upload, FileText, Trash2, CheckSquare, Square, MessageSquarePlus, Loader2, X, BookOpen } from 'lucide-react';
import axios from 'axios';
import './Sidebar.css';

const API_BASE = process.env.REACT_APP_API_URL || '';

export default function Sidebar({
  documents, setDocuments,
  selectedDocIds, setSelectedDocIds,
  isUploading, setIsUploading,
  onClearChat
}) {
  const fileInputRef = useRef(null);

  const handleFiles = useCallback(async (files) => {
    if (!files || files.length === 0) return;

    const pdfFiles = Array.from(files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
    if (pdfFiles.length === 0) {
      alert('Please upload PDF files only.');
      return;
    }

    setIsUploading(true);
    const formData = new FormData();
    pdfFiles.forEach(f => formData.append('files', f));

    try {
      // FIX: Removed the manual headers object! 
      // Axios handles the multipart boundary automatically now.
      const res = await axios.post(`${API_BASE}/upload`, formData);

      const newDocs = res.data.documents.filter(d => d.status === 'success');
      setDocuments(prev => [...prev, ...newDocs]);
      setSelectedDocIds(prev => [...prev, ...newDocs.map(d => d.doc_id)]);

      const errors = res.data.documents.filter(d => d.status === 'error');
      if (errors.length > 0) {
        alert(`Failed to process: ${errors.map(e => e.filename).join(', ')}`);
      }
    } catch (err) {
      const msg = err.response?.data?.detail || 'Upload failed. Is the backend running?';
      alert(msg);
    } finally {
      setIsUploading(false);
    }
  }, [setDocuments, setSelectedDocIds, setIsUploading]);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    handleFiles(e.dataTransfer.files);
  }, [handleFiles]);

  const handleDragOver = (e) => e.preventDefault();

  const toggleDoc = (docId) => {
    setSelectedDocIds(prev =>
      prev.includes(docId)
        ? prev.filter(id => id !== docId)
        : [...prev, docId]
    );
  };

  const removeDoc = async (docId) => {
    try {
      await axios.delete(`${API_BASE}/documents/${docId}`);
      setDocuments(prev => prev.filter(d => d.doc_id !== docId));
      setSelectedDocIds(prev => prev.filter(id => id !== docId));
    } catch {
      setDocuments(prev => prev.filter(d => d.doc_id !== docId));
      setSelectedDocIds(prev => prev.filter(id => id !== docId));
    }
  };

  const selectAll = () => setSelectedDocIds(documents.map(d => d.doc_id));
  const deselectAll = () => setSelectedDocIds([]);

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <BookOpen size={20} />
          <span>DocChat</span>
        </div>
        <button className="btn-icon" onClick={onClearChat} title="New conversation">
          <MessageSquarePlus size={16} />
        </button>
      </div>

      <div className="sidebar-section">
        <div
          className={`upload-zone ${isUploading ? 'uploading' : ''}`}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onClick={() => !isUploading && fileInputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={e => e.key === 'Enter' && fileInputRef.current?.click()}
        >
          {isUploading ? (
            <>
              <Loader2 size={24} className="spin" />
              <p>Processing PDFs…</p>
            </>
          ) : (
            <>
              <Upload size={24} />
              <p><strong>Drop PDFs here</strong></p>
              <p className="upload-hint">or click to browse · up to 50 MB</p>
            </>
          )}
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          multiple
          style={{ display: 'none' }}
          onChange={e => handleFiles(e.target.files)}
        />
      </div>

      {documents.length > 0 && (
        <div className="sidebar-section docs-section">
          <div className="section-header">
            <span className="section-title">Documents ({documents.length})</span>
            <div className="section-actions">
              <button className="btn-text" onClick={selectAll}>All</button>
              <button className="btn-text" onClick={deselectAll}>None</button>
            </div>
          </div>
          <div className="doc-list">
            {documents.map(doc => {
              const isSelected = selectedDocIds.includes(doc.doc_id);
              return (
                <div
                  key={doc.doc_id}
                  className={`doc-item ${isSelected ? 'selected' : ''}`}
                >
                  <button
                    className="doc-toggle"
                    onClick={() => toggleDoc(doc.doc_id)}
                  >
                    {isSelected
                      ? <CheckSquare size={14} className="check-icon" />
                      : <Square size={14} className="check-icon muted" />
                    }
                    <FileText size={14} className="file-icon" />
                    <div className="doc-info">
                      <span className="doc-name">{doc.filename}</span>
                      <span className="doc-meta">{doc.pages}p · {doc.chunks} chunks</span>
                    </div>
                  </button>
                  <button
                    className="btn-icon doc-delete"
                    onClick={() => removeDoc(doc.doc_id)}
                    title="Remove document"
                  >
                    <X size={12} />
                  </button>
                </div>
              );
            })}
          </div>
          {selectedDocIds.length > 0 && (
            <p className="selection-hint">
              Searching {selectedDocIds.length} of {documents.length} document{documents.length !== 1 ? 's' : ''}
            </p>
          )}
        </div>
      )}

      <div className="sidebar-footer">
        {/* FIX: Updated the footer branding */}
        <p>Powered by Gemini + ChromaDB</p>
      </div>
    </aside>
  );
}