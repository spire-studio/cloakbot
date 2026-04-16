import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  MessageSquare,
  PanelLeft,
  Send,
  Settings,
  Sparkles,
  Terminal,
  User,
} from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

import { Avatar } from './components/ui/avatar';
import { Button } from './components/ui/button';
import { ScrollArea } from './components/ui/scroll-area';
import { Sheet, SheetContent } from './components/ui/sheet';
import { Textarea } from './components/ui/textarea';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type Message = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
};

const navigation = [
  {
    name: 'Chat',
    icon: MessageSquare,
    id: 'chat',
    eyebrow: 'Workspace Assistant',
    description: 'Talk to Cloakbot about code, terminal output, and project context.',
  },
  {
    name: 'Configuration',
    icon: Settings,
    id: 'config',
    eyebrow: 'System Settings',
    description: 'Review workspace settings, tools, and execution preferences.',
  },
];

const workspaceBackground = {
  backgroundColor: 'hsl(51, 24%, 95%)',
};

const brandLogoPath = '/cloakbot-logo.png';

function NavigationPanel({
  currentTab,
  setCurrentTab,
  onToggleSidebar,
  collapsed = false,
}: {
  currentTab: string;
  setCurrentTab: (id: string) => void;
  onToggleSidebar?: () => void;
  collapsed?: boolean;
}) {
  return (
    <div className="flex h-full flex-col">
      <div className="px-3 pt-3">
        <div className={cn('flex items-center gap-3', collapsed && 'justify-center')}>
          {!collapsed && (
            <>
              <img src={brandLogoPath} alt="Cloakbot logo" className="h-11 w-11 shrink-0 object-contain" />
              <p className="min-w-0 flex-1 truncate text-xl font-bold text-foreground">Cloakbot</p>
            </>
          )}
          {onToggleSidebar && (
            <Button
              variant="ghost"
              size="icon"
              className={cn(
                'shrink-0 bg-transparent text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground cursor-ew-resize',
                collapsed ? 'h-10 w-full rounded-2xl px-0' : 'h-9 w-9 rounded-2xl'
              )}
              onClick={onToggleSidebar}
              aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              <PanelLeft className="size-4" />
            </Button>
          )}
        </div>
      </div>

      <nav className="px-3 pt-4">
        <div className="space-y-2">
          {navigation.map((item) => {
            const isActive = currentTab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setCurrentTab(item.id)}
                title={item.name}
                aria-label={item.name}
                className={cn(
                  'flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-left text-[13px] transition-colors',
                  collapsed && 'justify-center px-0',
                  isActive
                    ? 'bg-sidebar-accent text-sidebar-accent-foreground shadow-sm'
                    : 'text-sidebar-foreground/78 hover:bg-sidebar-accent/65 hover:text-sidebar-accent-foreground'
                )}
              >
                <item.icon className="size-4 shrink-0" />
                {!collapsed && <div className="min-w-0">
                  <div className="font-medium">{item.name}</div>
                </div>}
              </button>
            );
          })}
        </div>
      </nav>
    </div>
  );
}

function ShellHeader({
  currentTab,
  onOpenNavigation,
}: {
  currentTab: string;
  onOpenNavigation: () => void;
}) {
  const activeItem = navigation.find((item) => item.id === currentTab) ?? navigation[0];
  const ActiveIcon = activeItem.icon;

  return (
    <header className="border-b border-border/60 bg-background/82 px-4 py-4 backdrop-blur-xl md:px-6">
      <div className="flex items-center gap-3">
        <Button
          variant="outline"
          size="icon"
          className="shrink-0 rounded-2xl border-border/70 bg-card shadow-sm md:hidden"
          onClick={onOpenNavigation}
        >
          <PanelLeft className="size-4" />
        </Button>
        <div className="min-w-0 flex items-center gap-2">
          <ActiveIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
          <h1 className="truncate text-base font-semibold text-foreground">{activeItem.name}</h1>
        </div>
      </div>
    </header>
  );
}

function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content: 'Hello! I am Cloakbot. How can I assist you today?',
    },
  ]);
  const [input, setInput] = useState('');
  const wsRef = useRef<WebSocket | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/chat`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'assistant_message') {
        setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'assistant', content: data.content }]);
      } else if (data.type === 'assistant_delta') {
        setMessages((prev) => {
          const newMessages = [...prev];
          const lastMsg = newMessages[newMessages.length - 1];
          if (lastMsg && lastMsg.role === 'assistant') {
            lastMsg.content += data.content;
            return newMessages;
          }
          return [...newMessages, { id: Date.now().toString(), role: 'assistant', content: data.content }];
        });
      }
    };

    return () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      const scrollElement = scrollRef.current;
      scrollElement.scrollTop = scrollElement.scrollHeight;
    }
  }, [messages]);

  const handleSend = () => {
    if (!input.trim()) return;

    const newMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
    };

    setMessages((prev) => [...prev, newMsg]);

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ content: input.trim() }));
    }

    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-transparent">
      <ScrollArea className="min-h-0 flex-1 px-4 py-6 lg:px-6" ref={scrollRef}>
        <div className="mx-auto flex max-w-4xl flex-col gap-8 pb-4">
          {messages.length === 0 && (
            <div className="flex h-[50vh] flex-col items-center justify-center gap-4 text-muted-foreground opacity-50">
              <Sparkles className="h-12 w-12" />
              <p>Start a conversation with Cloakbot.</p>
            </div>
          )}
          {messages.map((msg) => (
            <div key={msg.id} className={cn('flex w-full gap-4', msg.role === 'user' ? 'flex-row-reverse' : '')}>
              <Avatar className="mt-0.5 h-8 w-8 shrink-0 ring-1 ring-border/20 shadow-sm">
                {msg.role === 'assistant' ? (
                  <div className="flex h-full w-full items-center justify-center rounded-full bg-primary/10 p-1">
                    <img src={brandLogoPath} alt="Cloakbot logo" className="h-full w-full object-contain" />
                  </div>
                ) : (
                  <div className="flex h-full w-full items-center justify-center rounded-full bg-secondary">
                    <User className="h-4 w-4 text-secondary-foreground" />
                  </div>
                )}
              </Avatar>
              <div
                className={cn(
                  'flex min-w-0 max-w-[85%] flex-col space-y-2',
                  msg.role === 'user' ? 'items-end' : 'items-start'
                )}
              >
                <div className="flex items-center gap-2 px-1">
                  <span className="text-xs font-medium text-muted-foreground">
                    {msg.role === 'assistant' ? 'Cloakbot' : 'You'}
                  </span>
                </div>
                <div
                  className={cn(
                    'text-[15px] leading-relaxed',
                    msg.role === 'assistant'
                      ? 'rounded-2xl rounded-tl-none border border-border bg-card px-5 py-4 text-card-foreground shadow-sm'
                      : 'rounded-2xl rounded-tr-none bg-primary px-5 py-3 text-primary-foreground shadow-sm'
                  )}
                >
                  <div className={cn('prose max-w-none break-words text-current', msg.role === 'user' ? 'prose-invert' : 'dark:prose-invert')}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>

      <div className="shrink-0 border-t border-border/60 bg-background/75 px-4 pb-6 pt-4 backdrop-blur-xl lg:px-6">
        <div className="relative mx-auto max-w-4xl">
          <div className="relative flex w-full items-end overflow-hidden rounded-xl border bg-card shadow-sm transition-shadow focus-within:ring-1 focus-within:ring-ring/50">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask Cloakbot anything..."
              className="m-0 min-h-[56px] max-h-[250px] w-full resize-none border-0 bg-transparent py-4 pl-4 pr-14 text-[15px] focus-visible:ring-0"
              rows={1}
            />
            <Button
              size="icon"
              className={cn(
                'absolute bottom-2 right-2 h-9 w-9 shrink-0 rounded-lg transition-all duration-200',
                input.trim() ? 'bg-primary text-primary-foreground opacity-100 hover:bg-primary/90' : 'bg-secondary text-muted-foreground opacity-50'
              )}
              onClick={handleSend}
              disabled={!input.trim()}
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
          <div className="mt-3 text-center text-xs text-muted-foreground">
            Cloakbot can make mistakes. Check important info.
          </div>
        </div>
      </div>
    </div>
  );
}

function ConfigPlaceholder() {
  return (
    <div className="flex min-h-0 flex-1 flex-col bg-transparent">
      <div className="flex-1 overflow-auto p-6 lg:p-8">
        <div className="mx-auto max-w-4xl">
          <div className="mb-8">
            <h1 className="text-3xl font-bold tracking-tight">Configuration</h1>
            <p className="mt-2 text-muted-foreground">
              Manage your workspace settings and preferences.
            </p>
          </div>

          <div className="mb-6 rounded-3xl border border-border/70 bg-card/85 p-6 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-secondary text-secondary-foreground">
                <Terminal className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-medium text-foreground">Workspace Profile</p>
                <p className="text-sm text-muted-foreground">Use this area to manage runtime defaults before adding advanced controls.</p>
              </div>
            </div>
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            <div className="rounded-3xl border bg-card/85 p-6 text-card-foreground shadow-sm">
              <Settings className="mb-4 h-8 w-8 text-muted-foreground" />
              <h3 className="mb-2 text-lg font-semibold">General Settings</h3>
              <p className="mb-4 text-sm text-muted-foreground">
                Configure basic options for your agent, including timeouts and memory limits.
              </p>
              <Button variant="outline" className="w-full">Configure</Button>
            </div>

            <div className="rounded-3xl border bg-card/85 p-6 text-card-foreground shadow-sm">
              <Terminal className="mb-4 h-8 w-8 text-muted-foreground" />
              <h3 className="mb-2 text-lg font-semibold">Tools & Plugins</h3>
              <p className="mb-4 text-sm text-muted-foreground">
                Manage the tools and plugins available to the agent during execution.
              </p>
              <Button variant="outline" className="w-full">Manage Tools</Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function WorkspacePanel({
  currentTab,
  onOpenNavigation,
  className,
}: {
  currentTab: string;
  onOpenNavigation: () => void;
  className?: string;
}) {
  return (
    <div className={cn('flex min-h-svh min-w-0 flex-1 flex-col overflow-hidden bg-background/88', className)} style={workspaceBackground}>
      <ShellHeader currentTab={currentTab} onOpenNavigation={onOpenNavigation} />
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {currentTab === 'chat' && <ChatInterface />}
        {currentTab === 'config' && <ConfigPlaceholder />}
      </main>
    </div>
  );
}

export default function App() {
  const [currentTab, setCurrentTab] = useState('chat');
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const [desktopSidebarCollapsed, setDesktopSidebarCollapsed] = useState(false);

  const handleTabChange = (id: string) => {
    setCurrentTab(id);
    setMobileNavigationOpen(false);
  };

  return (
    <div className="min-h-svh bg-background" style={workspaceBackground}>
      <div className="min-h-svh md:min-h-0 md:p-3">
        <div className="hidden min-h-[calc(100svh-1.5rem)] overflow-hidden rounded-[30px] border border-border/60 shadow-[0_24px_80px_rgba(61,57,41,0.12)] md:flex">
          <aside
            className={cn(
              'shrink-0 border-r border-sidebar-border/70 bg-sidebar/92 transition-[width] duration-200',
              desktopSidebarCollapsed ? 'w-[88px]' : 'w-[240px]'
            )}
          >
            <NavigationPanel
              currentTab={currentTab}
              setCurrentTab={handleTabChange}
              onToggleSidebar={() => setDesktopSidebarCollapsed((prev) => !prev)}
              collapsed={desktopSidebarCollapsed}
            />
          </aside>
          <WorkspacePanel
            currentTab={currentTab}
            onOpenNavigation={() => setMobileNavigationOpen(true)}
            className="min-h-[calc(100svh-1.5rem)]"
          />
        </div>

        <WorkspacePanel
          currentTab={currentTab}
          onOpenNavigation={() => setMobileNavigationOpen(true)}
          className="md:hidden"
        />
      </div>

      <Sheet open={mobileNavigationOpen} onOpenChange={setMobileNavigationOpen}>
        <SheetContent side="left" className="w-[290px] border-r border-sidebar-border bg-sidebar p-0 sm:max-w-[290px]">
          <NavigationPanel currentTab={currentTab} setCurrentTab={handleTabChange} />
        </SheetContent>
      </Sheet>
    </div>
  );
}
