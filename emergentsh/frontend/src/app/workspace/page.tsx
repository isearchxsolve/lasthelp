'use client';

import { useState, useEffect, useRef } from 'react';
import { Send, Loader2, X, Copy, Download, Github, Terminal, Layers, Zap, CheckCircle, AlertCircle, MessageSquare, Monitor, Code, Settings } from 'lucide-react';

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  agent?: string;
  timestamp: Date;
  metadata?: Record<string, unknown>;
}

interface AgentActivity {
  id: string;
  agent: string;
  status: 'planning' | 'coding' | 'testing' | 'deploying' | 'complete' | 'error';
  message: string;
  timestamp: Date;
}

const agents = [
  { name: 'Orchestrator', icon: Layers, color: 'from-purple-500 to-purple-700' },
  { name: 'Frontend', icon: Monitor, color: 'from-blue-500 to-blue-700' },
  { name: 'Backend', icon: Terminal, color: 'from-green-500 to-green-700' },
  { name: 'Database', icon: Code, color: 'from-amber-500 to-amber-700' },
  { name: 'Tester', icon: CheckCircle, color: 'from-red-500 to-red-700' },
  { name: 'Deployer', icon: Zap, color: 'from-cyan-500 to-cyan-700' },
];

export default function WorkspacePage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      agent: 'Orchestrator',
      content: 'Welcome to Emergent! I\'m your Orchestrator agent. Describe the app you want to build, and my team will plan, code, test, and deploy it for you.',
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [activities, setActivities] = useState<AgentActivity[]>([]);
  const [currentPhase, setCurrentPhase] = useState<'planning' | 'coding' | 'testing' | 'deploying' | 'complete'>('planning');
  const [previewUrl, setPreviewUrl] = useState('http://localhost:3001');
  const [showPreview, setShowPreview] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    // Simulate agent response
    setTimeout(() => {
      const phases: Array<'planning' | 'coding' | 'testing' | 'deploying' | 'complete'> = 
        ['planning', 'coding', 'testing', 'deploying', 'complete'];
      let phaseIndex = 0;

      const interval = setInterval(() => {
        if (phaseIndex >= phases.length) {
          clearInterval(interval);
          setIsLoading(false);
          return;
        }

        const phase = phases[phaseIndex];
        setCurrentPhase(phase);

        const agent = agents[phaseIndex % agents.length];
        
        setActivities(prev => [...prev, {
          id: Date.now().toString(),
          agent: agent.name,
          status: phase,
          message: `${agent.name} is ${phase}...`,
          timestamp: new Date(),
        }]);

        phaseIndex++;
      }, 2000);

      // Add assistant response after all phases
      setTimeout(() => {
        const assistantMessage: Message = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          agent: 'Orchestrator',
          content: `I've completed building your app! The multi-agent team has finished all phases. You can now preview the live app, iterate with more instructions, or export the code.`,
          timestamp: new Date(),
        };
        setMessages(prev => [...prev, assistantMessage]);
      }, phases.length * 2000 + 1000);

    }, 1000);
  };

  return (
    <div className="h-screen flex bg-dark-950 overflow-hidden">
      {/* Left Sidebar - Agent Activity */}
      {sidebarOpen && (
        <aside className="w-80 bg-dark-900 border-r border-dark-800 flex flex-col hidden lg:flex">
          <div className="p-4 border-b border-dark-800">
            <h3 className="font-semibold text-white flex items-center gap-2">
              <Zap className="w-5 h-5 text-primary-500" />
              Agent Activity
            </h3>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {activities.length === 0 ? (
              <div className="text-center text-dark-500 py-8">
                <MessageSquare className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p className="text-sm">Start a conversation to see agent activity</p>
              </div>
            ) : (
              activities.map((activity) => (
                <div key={activity.id} className="p-3 bg-dark-800/50 rounded-xl border border-dark-700">
                  <div className="flex items-center gap-2 mb-1">
                    <div className={`w-2 h-2 rounded-full ${
                      activity.status === 'complete' ? 'bg-green-500' :
                      activity.status === 'error' ? 'bg-red-500' :
                      'bg-primary-500 animate-pulse'
                    }`} />
                    <span className="text-xs font-medium text-white capitalize">{activity.agent}</span>
                    <span className="text-xs text-dark-500">{activity.status}</span>
                  </div>
                  <p className="text-xs text-dark-400">{activity.message}</p>
                  <p className="text-xs text-dark-500 mt-1">{activity.timestamp.toLocaleTimeString()}</p>
                </div>
              ))
            )}
          </div>
          <div className="p-4 border-t border-dark-800">
            <div className="flex items-center gap-3 p-3 bg-dark-800/50 rounded-xl border border-dark-700">
              <div className={`w-3 h-3 rounded-full ${
                currentPhase === 'complete' ? 'bg-green-500' :
                currentPhase === 'error' ? 'bg-red-500' :
                'bg-primary-500 animate-pulse'
              }`} />
              <div>
                <p className="text-xs text-dark-500">Current Phase</p>
                <p className="text-sm font-medium text-white capitalize">{currentPhase}</p>
              </div>
            </div>
          </div>
        </aside>
      )}

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Chat Header */}
        <header className="h-16 bg-dark-900 border-b border-dark-800 flex items-center justify-between px-4">
          <div className="flex items-center gap-3">
            <h2 className="font-semibold text-white">Project Workspace</h2>
            <span className="px-2 py-1 text-xs bg-primary-500/10 text-primary-400 rounded-full">v1.0.0</span>
          </div>
          <div className="flex items-center gap-2">
            <button className="p-2 text-dark-400 hover:text-white hover:bg-dark-800 rounded-lg transition-colors" title="Settings">
              <Settings className="w-5 h-5" />
            </button>
            <button className="p-2 text-dark-400 hover:text-white hover:bg-dark-800 rounded-lg transition-colors" title="Toggle Sidebar">
              <Layers className="w-5 h-5" />
            </button>
          </div>
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-6" ref={messagesEndRef}>
          {messages.map((message) => (
            <div key={message.id} className={`flex gap-3 ${message.role === 'user' ? 'flex-row-reverse' : ''}`}>
              <div className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 ${
                message.role === 'user' 
                  ? 'bg-primary-500' 
                  : message.role === 'system' 
                    ? 'bg-amber-500' 
                    : 'bg-dark-800 border border-dark-700'
              }`}>
                {message.role === 'user' ? (
                  <span className="text-white text-sm font-medium">U</span>
                ) : message.role === 'system' ? (
                  <AlertCircle className="w-4 h-4 text-amber-400" />
                ) : (
                  <Terminal className="w-4 h-4 text-primary-400" />
                )}
              </div>
              <div className={`max-w-[70%] ${message.role === 'user' ? 'text-right' : ''}`}>
                <div className={`inline-block p-4 rounded-2xl ${
                  message.role === 'user' 
                    ? 'bg-primary-500/20 text-white' 
                    : 'bg-dark-800/50 border border-dark-700 text-white'
                }`}>
                  {message.agent && (
                    <p className="text-xs text-primary-400 mb-1 font-medium">{message.agent}</p>
                  )}
                  <p className="whitespace-pre-wrap">{message.content}</p>
                </div>
                <p className="text-xs text-dark-500 mt-1">{message.timestamp.toLocaleTimeString()}</p>
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="p-4 border-t border-dark-800 bg-dark-900/50 backdrop-blur-sm">
          <form onSubmit={handleSubmit} className="flex gap-3">
            <div className="flex-1 relative">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Type your message... (Shift+Enter for new line)"
                className="w-full bg-dark-800 border border-dark-700 text-white placeholder-dark-500 px-4 py-3 rounded-xl focus:outline-none focus:border-primary-500 resize-none min-h-[50px] max-h-[150px]"
                rows={1}
                disabled={isLoading}
              />
            </div>
            <button
              type="submit"
              disabled={isLoading || !input.trim()}
              className="p-3 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl text-white transition-colors flex items-center justify-center"
            >
              {isLoading ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Send className="w-5 h-5" />
              )}
            </button>
          </form>
          <p className="text-xs text-dark-500 text-center mt-2">
            Press Enter to send • Shift+Enter for new line
          </p>
        </div>
      </div>

      {/* Right Panel - Live Preview */}
      {showPreview && (
        <aside className="w-96 bg-dark-900 border-l border-dark-800 flex flex-col hidden xl:flex">
          <div className="p-4 border-b border-dark-800 flex items-center justify-between">
            <h3 className="font-semibold text-white flex items-center gap-2">
              <Monitor className="w-5 h-5 text-primary-500" />
              Live Preview
            </h3>
            <div className="flex items-center gap-2">
              <button className="p-2 text-dark-400 hover:text-white hover:bg-dark-800 rounded-lg transition-colors" title="Refresh">
                <Loader2 className="w-4 h-4" />
              </button>
              <button className="p-2 text-dark-400 hover:text-white hover:bg-dark-800 rounded-lg transition-colors" title="Open in new tab">
                <Monitor className="w-4 h-4" />
              </button>
            </div>
          </div>
          <div className="flex-1 relative">
            <iframe
              src={previewUrl}
              className="w-full h-full border-0"
              title="Live Preview"
              sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
            />
            <div className="absolute bottom-4 right-4 flex gap-2">
              <button className="p-2 bg-dark-900/80 backdrop-blur rounded-lg text-dark-300 hover:text-white transition-colors" title="Copy URL">
                <Copy className="w-4 h-4" />
              </button>
              <button className="p-2 bg-primary-600 hover:bg-primary-700 rounded-lg text-white transition-colors" title="Download Code">
                <Download className="w-4 h-4" />
              </button>
              <button className="p-2 bg-dark-900/80 backdrop-blur rounded-lg text-dark-300 hover:text-white transition-colors" title="GitHub Sync">
                <Github className="w-4 h-4" />
              </button>
            </div>
          </div>
          <div className="p-4 border-t border-dark-800 bg-dark-950/50">
            <div className="flex items-center gap-2 text-xs text-dark-400">
              <span className="w-2 h-2 bg-green-500 rounded-full" />
              <span>Preview server running on port 3001</span>
            </div>
          </div>
        </aside>
      )}
    </div>
  );
}