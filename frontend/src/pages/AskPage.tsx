import { useState, useRef, useEffect } from 'react';
import { api } from '../api/client';
import { fetchFarms } from '../api/farms';

export default function AskPage() {
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState<{role: 'user' | 'bot', text: string}[]>([]);
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSubmit = async (text: string) => {
    if (!text.trim() || loading) return;

    const userText = text.trim();
    setMessages(prev => [...prev, { role: 'user', text: userText }]);
    setQuery('');
    setLoading(true);

    try {
      const farmsList = await fetchFarms();
      if (!farmsList.farms || farmsList.farms.length === 0) {
        setMessages(prev => [...prev, { role: 'bot', text: 'No farms available to query.' }]);
        return;
      }
      const farmId = farmsList.farms[0].farm_id;
      
      const payload = {
        language: 'en',
        text: userText,
        tier: 'rules_only'
      };
      
      const response = await api.post<any>(`/farms/${farmId}/voice-query`, payload);
      setMessages(prev => [...prev, { role: 'bot', text: response.answer_text || 'No answer available.' }]);
    } catch (err) {
      console.error(err);
      setMessages(prev => [...prev, { role: 'bot', text: 'Sorry, I encountered an error connecting to FARMIGLE.' }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col w-full h-[calc(100vh-80px)] bg-[#FAFDFB]">
      {/* Header */}
      <div className="px-margin pt-space-md pb-3 bg-white border-b border-surface-variant flex items-center gap-3 sticky top-0 z-10 shadow-sm">
        <div className="w-10 h-10 rounded-full bg-[#E8F3ED] flex items-center justify-center text-primary border border-[#d5e8de]">
          <span className="material-symbols-outlined text-[24px]">psychology</span>
        </div>
        <div>
          <h1 className="text-[18px] font-medium text-primary tracking-tight leading-none">Farmigle Assistant</h1>
          <p className="text-[10px] text-secondary font-technical-label tracking-widest mt-1 uppercase">AI Agronomist • Online</p>
        </div>
      </div>
      
      <div className="flex-1 overflow-y-auto flex flex-col gap-space-sm p-margin pb-6">
        {messages.length === 0 && (
          <div className="flex flex-col h-full justify-center gap-6">
            <div className="text-center text-primary/60 font-body-default px-6">
              I'm your AI farm assistant. How can I help you today?
            </div>
            <div className="flex flex-col gap-2 w-full">
              <button onClick={() => handleSubmit("What should I do about my farm today?")} className="w-full text-left bg-white border border-surface-variant p-3 rounded-[12px] text-[14px] text-primary shadow-sm hover:bg-[#E8F3ED] transition-colors">
                "What should I do about my farm today?"
              </button>
              <button onClick={() => handleSubmit("Which zone is ready for harvest?")} className="w-full text-left bg-white border border-surface-variant p-3 rounded-[12px] text-[14px] text-primary shadow-sm hover:bg-[#E8F3ED] transition-colors">
                "Which zone is ready for harvest?"
              </button>
              <button onClick={() => handleSubmit("Summarize my farm's health.")} className="w-full text-left bg-white border border-surface-variant p-3 rounded-[12px] text-[14px] text-primary shadow-sm hover:bg-[#E8F3ED] transition-colors">
                "Summarize my farm's health."
              </button>
            </div>
          </div>
        )}
        
        {messages.map((msg, i) => (
          <div key={i} className={`flex w-full ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] p-3 text-[15px] leading-snug shadow-sm ${
              msg.role === 'user' 
                ? 'bg-[#183C32] text-white rounded-[16px] rounded-tr-sm' 
                : 'bg-white border border-surface-variant text-on-surface rounded-[16px] rounded-tl-sm'
            }`}>
              {msg.text}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-white border border-surface-variant text-on-surface-variant p-3 rounded-[16px] rounded-tl-sm text-[14px] flex items-center gap-2 shadow-sm">
              <span className="w-1.5 h-1.5 bg-primary/40 rounded-full animate-pulse"></span>
              <span className="w-1.5 h-1.5 bg-primary/60 rounded-full animate-pulse" style={{ animationDelay: '0.2s' }}></span>
              <span className="w-1.5 h-1.5 bg-primary/80 rounded-full animate-pulse" style={{ animationDelay: '0.4s' }}></span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input Form */}
      <div className="bg-white border-t border-surface-variant p-margin pb-safe sticky bottom-0">
        <form onSubmit={(e) => { e.preventDefault(); if (!loading) handleSubmit(query); }} className="flex gap-2">
          <input 
            type="text" 
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask about your harvest..." 
            className="flex-1 bg-surface-container-lowest border border-surface-variant rounded-full pl-4 pr-12 py-3 text-[15px] text-on-surface outline-none focus:border-primary focus:ring-1 focus:ring-primary shadow-inner"
            disabled={loading}
          />
          <button 
            type="submit" 
            disabled={loading || !query.trim()}
            className="h-12 w-12 flex-shrink-0 flex items-center justify-center rounded-full bg-[#183C32] text-white disabled:bg-surface-variant disabled:text-on-surface-variant shadow-sm transition-colors"
          >
            <span className="material-symbols-outlined text-[20px]">send</span>
          </button>
        </form>
      </div>
    </div>
  );
}
