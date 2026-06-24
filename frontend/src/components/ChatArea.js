import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Loader2, FileQuestion, Sparkles } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm'; // ADDED: Import the GitHub Flavored Markdown plugin
import SourceCard from './SourceCard';
import './ChatArea.css';

const API_BASE = process.env.REACT_APP_API_URL || '';

const EXAMPLE_QUESTIONS = [
  "Summarize the main topics in this document",
  "What are the key findings or conclusions?",
  "List the most important points",
  "What data or evidence is presented?",
];

export default function ChatArea({ documents, selectedDocIds, messages, addMessage, updateLastMessage }) {
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);
  const conversationHistoryRef = useRef([]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = useCallback(async (question) => {
    if (!question.trim() || isStreaming) return;
    if (documents.length === 0) {
      addMessage({
        id: Date.now(),
        role: 'assistant',
        content: 'Please upload at least one PDF document before asking questions.',
        sources: [],
        isError: true,
      });
      return;
    }
    if (selectedDocIds.length === 0) {
      addMessage({
        id: Date.now(),
        role: 'assistant',
        content: 'Please select at least one document from the sidebar to search.',
        sources: [],
        isError: true,
      });
      return;
    }

    const userMsg = {
      id: Date.now(),
      role: 'user',
      content: question,
    };
    addMessage(userMsg);
    setInput('');
    setIsStreaming(true);

    const assistantMsg = {
      id: Date.now() + 1,
      role: 'assistant',
      content: '',
      sources: [],
      isStreaming: true,
    };
    addMessage(assistantMsg);

    try {
      const response = await fetch(`${API_BASE}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question,
          conversation_history: conversationHistoryRef.current,
          doc_ids: selectedDocIds.length > 0 ? selectedDocIds : null,
        }),
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let fullAnswer = '';
      let sources = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6).trim();
          if (data === '[DONE]') continue;

          try {
            const parsed = JSON.parse(data);
            if (parsed.type === 'sources') {
              sources = parsed.sources;
              updateLastMessage(prev => ({ ...prev, sources }));
            } else if (parsed.type === 'text') {
              fullAnswer += parsed.text;
              updateLastMessage(prev => ({
                ...prev,
                content: fullAnswer,
                sources,
              }));
            } else if (parsed.type === 'done') {
              fullAnswer = parsed.answer || fullAnswer;
            } else if (parsed.type === 'error') {
              updateLastMessage(prev => ({
                ...prev,
                content: parsed.text,
                isError: true,
              }));
            }
          } catch {}
        }
      }

      updateLastMessage(prev => ({ ...prev, isStreaming: false }));

      conversationHistoryRef.current = [
        ...conversationHistoryRef.current,
        { role: 'user', content: question },
        { role: 'assistant', content: fullAnswer },
      ].slice(-20); // keep last 20 messages

    } catch (err) {
      updateLastMessage(prev => ({
        ...prev,
        content: `Error: ${err.message}. Make sure the backend server is running.`,
        isError: true,
        isStreaming: false,
      }));
    } finally {
      setIsStreaming(false);
    }
  }, [documents, selectedDocIds, isStreaming, addMessage, updateLastMessage]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  const handleTextareaInput = (e) => {
    setInput(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
  };

  const isEmpty = messages.length === 0;

  return (
    <div className="chat-area">
      <div className="chat-header">
        <div className="chat-header-info">
          <Sparkles size={16} className="header-icon" />
          <span>Ask anything about your documents</span>
        </div>
        {selectedDocIds.length > 0 && (
          <span className="search-scope">
            {selectedDocIds.length} doc{selectedDocIds.length !== 1 ? 's' : ''} selected
          </span>
        )}
      </div>

      <div className="messages-container">
        {isEmpty ? (
          <div className="empty-state">
            <div className="empty-icon">
              <FileQuestion size={40} />
            </div>
            <h2>Start a conversation</h2>
            <p>Upload PDFs from the sidebar, then ask questions about them.</p>
            {documents.length > 0 && (
              <div className="example-questions">
                <p className="examples-label">Try asking:</p>
                <div className="examples-grid">
                  {EXAMPLE_QUESTIONS.map((q, i) => (
                    <button
                      key={i}
                      className="example-btn"
                      onClick={() => sendMessage(q)}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <>
            {messages.map(msg => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      <div className="chat-input-area">
        <div className="input-wrapper">
          <textarea
            ref={textareaRef}
            className="chat-input"
            value={input}
            onChange={handleTextareaInput}
            onKeyDown={handleKeyDown}
            placeholder={documents.length === 0 ? "Upload a PDF to get started…" : "Ask a question about your documents…"}
            disabled={isStreaming || documents.length === 0}
            rows={1}
          />
          <button
            className={`send-btn ${isStreaming ? 'loading' : ''}`}
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || isStreaming || documents.length === 0}
          >
            {isStreaming
              ? <Loader2 size={16} className="spin" />
              : <Send size={16} />
            }
          </button>
        </div>
        <p className="input-hint">Press Enter to send · Shift+Enter for new line</p>
      </div>
    </div>
  );
}

function MessageBubble({ message }) {
  const isUser = message.role === 'user';

  return (
    <div className={`message-wrapper ${isUser ? 'user' : 'assistant'}`}>
      <div className={`message-bubble ${isUser ? 'user' : 'assistant'} ${message.isError ? 'error' : ''}`}>
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          <>
            {message.content ? (
              <div className="markdown-content">
                {/* ADDED: The remarkPlugins property to render tables correctly */}
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {message.content}
                </ReactMarkdown>
              </div>
            ) : (
              <div className="thinking">
                <Loader2 size={14} className="spin" />
                <span>Searching documents…</span>
              </div>
            )}
            {message.isStreaming && message.content && (
              <span className="cursor-blink">▋</span>
            )}
          </>
        )}
      </div>
      {!isUser && message.sources && message.sources.length > 0 && (
        <div className="sources-section">
          <p className="sources-label">Sources</p>
          <div className="sources-list">
            {message.sources.map((source, i) => (
              <SourceCard key={i} source={source} index={i + 1} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}