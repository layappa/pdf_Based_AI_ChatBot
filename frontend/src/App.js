import React, { useState, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import './App.css';

function App() {
  const [documents, setDocuments] = useState([]);
  const [selectedDocIds, setSelectedDocIds] = useState([]);
  const [messages, setMessages] = useState([]);
  const [isUploading, setIsUploading] = useState(false);

  const addMessage = useCallback((message) => {
    setMessages(prev => [...prev, message]);
  }, []);

  const updateLastMessage = useCallback((updater) => {
    setMessages(prev => {
      const updated = [...prev];
      const last = updated[updated.length - 1];
      updated[updated.length - 1] = typeof updater === 'function' ? updater(last) : { ...last, ...updater };
      return updated;
    });
  }, []);

  const clearChat = useCallback(() => {
    setMessages([]);
  }, []);

  return (
    <div className="app">
      <Sidebar
        documents={documents}
        setDocuments={setDocuments}
        selectedDocIds={selectedDocIds}
        setSelectedDocIds={setSelectedDocIds}
        isUploading={isUploading}
        setIsUploading={setIsUploading}
        onClearChat={clearChat}
      />
      <main className="app-main">
        <ChatArea
          documents={documents}
          selectedDocIds={selectedDocIds}
          messages={messages}
          addMessage={addMessage}
          updateLastMessage={updateLastMessage}
        />
      </main>
    </div>
  );
}

export default App;
