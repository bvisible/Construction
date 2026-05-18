import type { ChatMessage } from '../../types';
import MessageThread from './MessageThread';
import InputBar from './InputBar';

interface ChatLeftPanelProps {
  messages: ChatMessage[];
  isStreaming: boolean;
  suggestions: string[];
  onSend: (text: string) => void;
  onClear: () => void;
  aiConfigured: boolean | null;
}

export default function ChatLeftPanel({ messages, isStreaming, suggestions, onSend, onClear, aiConfigured }: ChatLeftPanelProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: 'var(--chat-bg)',
        fontFamily: 'var(--chat-font-body)',
      }}
    >
      <MessageThread messages={messages} isStreaming={isStreaming} aiConfigured={aiConfigured} />
      <InputBar
        onSend={onSend}
        onClear={onClear}
        hasMessages={messages.length > 0}
        isStreaming={isStreaming}
        suggestions={suggestions}
      />
    </div>
  );
}
