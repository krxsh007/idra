import React, { useState } from 'react';
import { MessageSquare, X, Send, AlertTriangle, PhoneCall, Building2, BookOpen } from 'lucide-react';
import { api } from '../../lib/api';
import { CitizenQueryResponse } from '../../types/api';

interface CitizenChatDrawerProps {
  eventId?: string;
}

interface ChatMessageItem {
  role: 'user' | 'assistant';
  content: string;
  response?: CitizenQueryResponse;
}

export const CitizenChatDrawer: React.FC<CitizenChatDrawerProps> = ({ eventId }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || isLoading) return;

    const userText = query.trim();
    setQuery('');
    setError(null);
    setMessages((prev) => [...prev, { role: 'user', content: userText }]);
    setIsLoading(true);

    try {
      const res = await api.queryAssistant({
        query: userText,
        session_id: sessionId,
        event_id: eventId,
      });
      setSessionId(res.session_id);
      setMessages((prev) => [...prev, { role: 'assistant', content: res.answer, response: res }]);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Assistant query failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      {/* Floating Toggle Button */}
      {!isOpen && (
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          className="absolute bottom-10 right-4 z-40 flex items-center gap-2 px-4 py-3 bg-gradient-to-r from-amber-600 to-amber-500 hover:from-amber-500 hover:to-amber-400 text-white font-semibold text-xs rounded-full shadow-2xl transition-transform hover:scale-105"
        >
          <MessageSquare className="w-4 h-4" />
          <span>Citizen Emergency Assistant</span>
        </button>
      )}

      {/* Slide-out Drawer */}
      {isOpen && (
        <div className="absolute bottom-10 right-4 z-50 w-96 max-w-[calc(100%-2rem)] max-h-[calc(100%-3.5rem)] h-[550px] bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
          {/* Header */}
          <div className="p-3.5 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <MessageSquare className="w-4 h-4 text-amber-400" />
              <div>
                <h4 className="text-xs font-bold text-slate-100">IDRA Citizen Assistant</h4>
                <p className="text-[10px] text-slate-400">Grounded Emergency Safety Advice</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="text-slate-400 hover:text-slate-200 p-1 rounded"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Official Helpline Callout Banner */}
          <div className="bg-amber-950/60 border-b border-amber-800/40 p-2.5 text-[11px] text-amber-200 flex items-center gap-2">
            <PhoneCall className="w-4 h-4 text-amber-400 flex-shrink-0" />
            <div>
              <strong>Emergency Helplines:</strong> National: <strong>112</strong> | State: <strong>1070</strong> | Chennai: <strong>1077</strong>
            </div>
          </div>

          {/* Chat Messages Body */}
          <div className="flex-1 overflow-y-auto p-3.5 space-y-3">
            {messages.length === 0 && (
              <div className="text-center py-10 px-4 text-xs text-slate-400">
                <p className="font-semibold text-slate-300 mb-1">How can we assist you?</p>
                <p className="text-[11px] leading-relaxed">
                  Ask about flood water safety, nearby relief shelters, grab bags, or emergency evacuation procedures.
                </p>
              </div>
            )}

            {messages.map((m, idx) => (
              <div
                key={idx}
                className={`flex flex-col ${m.role === 'user' ? 'items-end' : 'items-start'}`}
              >
                <div
                  className={`p-3 rounded-xl text-xs max-w-[90%] leading-relaxed ${
                    m.role === 'user'
                      ? 'bg-amber-600 text-white rounded-br-none'
                      : 'bg-slate-950 border border-slate-800 text-slate-200 rounded-bl-none'
                  }`}
                >
                  {m.content}

                  {/* Escalation Warning */}
                  {m.response?.escalated && (
                    <div className="mt-2 pt-2 border-t border-rose-800/50 text-[11px] text-rose-300 font-medium flex items-center gap-1.5">
                      <AlertTriangle className="w-3.5 h-3.5 text-rose-400 flex-shrink-0" />
                      <span>Report escalated to emergency responders. Call 112 immediately.</span>
                    </div>
                  )}

                  {/* Nearest Facilities Surfaced */}
                  {m.response?.nearest_facilities && m.response.nearest_facilities.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-slate-800 text-[11px]">
                      <span className="font-semibold text-slate-300 flex items-center gap-1 mb-1">
                        <Building2 className="w-3 h-3 text-sky-400" />
                        Nearest Operational Facilities:
                      </span>
                      {m.response.nearest_facilities.map((fac) => (
                        <div key={fac.facility_id} className="text-slate-400 pl-2">
                          • {fac.name} ({fac.facility_type}, {(fac.distance_m / 1000).toFixed(1)} km)
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Grounded Citations */}
                  {m.response?.citations && m.response.citations.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-slate-800 text-[10px] text-slate-400 flex items-center gap-1">
                      <BookOpen className="w-3 h-3 text-amber-400" />
                      <span>Source: {m.response.citations[0].document_title}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {isLoading && (
              <div className="text-xs text-amber-400 animate-pulse pl-2">
                Retrieving verified disaster guidelines...
              </div>
            )}

            {error && (
              <div className="p-2 rounded bg-rose-950/50 border border-rose-800 text-xs text-rose-300">
                {error}
              </div>
            )}
          </div>

          {/* Input Form */}
          <form onSubmit={handleSend} className="p-2.5 bg-slate-950 border-t border-slate-800 flex gap-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask safety advice or report conditions..."
              className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-amber-500"
            />
            <button
              type="submit"
              disabled={isLoading || !query.trim()}
              className="p-2 bg-amber-600 hover:bg-amber-500 disabled:bg-slate-800 text-white rounded-lg transition-colors"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </form>
        </div>
      )}
    </>
  );
};
