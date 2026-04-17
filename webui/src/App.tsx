import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  ChevronLeft,
  ChevronRight,
  MessageSquare,
  PanelLeft,
  Send,
  Settings,
  Shield,
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
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from './components/ui/tooltip';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type Message = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  privacyAnnotations?: PrivacyAnnotation[];
};

type PrivacyAnnotation = {
  placeholder: string;
  text: string;
  start: number;
  end: number;
  entity_type: string;
  severity: 'high' | 'medium' | 'low';
  canonical: string;
  aliases: string[];
  value: string | number | null;
};

type PrivacySummary = {
  entity_type: string;
  severity: 'high' | 'medium' | 'low';
  count: number;
};

type PrivacyEntity = {
  placeholder: string;
  entity_type: string;
  severity: 'high' | 'medium' | 'low';
  canonical: string;
  aliases: string[];
  value: string | number | null;
  created_turn: string | null;
  last_seen_turn: string | null;
};

type PrivacySnapshot = {
  total_entities: number;
  entities: PrivacyEntity[];
  entity_counts: PrivacySummary[];
};

const emptyPrivacySnapshot: PrivacySnapshot = {
  total_entities: 0,
  entities: [],
  entity_counts: [],
};

type MarkdownNode = {
  type: string;
  value?: string;
  children?: MarkdownNode[];
  tagName?: string;
  properties?: Record<string, unknown>;
  position?: {
    start?: {
      offset?: number;
    };
    end?: {
      offset?: number;
    };
  };
};

function splitTextNodeByPrivacyAnnotations(
  node: MarkdownNode,
  annotations: PrivacyAnnotation[],
): MarkdownNode[] | null {
  if (typeof node.value !== 'string') {
    return null;
  }

  const start = node.position?.start?.offset;
  const end = node.position?.end?.offset;
  if (typeof start !== 'number' || typeof end !== 'number' || start >= end) {
    return null;
  }

  const overlapping = annotations.filter((annotation) => annotation.start < end && annotation.end > start);
  if (overlapping.length === 0) {
    return null;
  }

  const fragments: MarkdownNode[] = [];
  let cursor = start;

  for (const [annotationIndex, annotation] of annotations.entries()) {
    if (annotation.start >= end || annotation.end <= start) {
      continue;
    }

    const segmentStart = Math.max(annotation.start, start);
    const segmentEnd = Math.min(annotation.end, end);
    if (segmentStart > cursor) {
      fragments.push({
        type: 'text',
        value: node.value.slice(cursor - start, segmentStart - start),
      });
    }

    fragments.push({
      type: 'element',
      tagName: 'span',
      properties: {
        dataPrivacyIndex: String(annotationIndex),
      },
      children: [
        {
          type: 'text',
          value: node.value.slice(segmentStart - start, segmentEnd - start),
        },
      ],
    });
    cursor = segmentEnd;
  }

  if (cursor < end) {
    fragments.push({
      type: 'text',
      value: node.value.slice(cursor - start),
    });
  }

  return fragments;
}

function annotateMarkdownTree(node: MarkdownNode, annotations: PrivacyAnnotation[]) {
  if (!Array.isArray(node.children)) {
    return;
  }

  for (let index = node.children.length - 1; index >= 0; index -= 1) {
    const child = node.children[index];
    if (child.type === 'text') {
      const fragments = splitTextNodeByPrivacyAnnotations(child, annotations);
      if (fragments) {
        node.children.splice(index, 1, ...fragments);
        continue;
      }
    }

    annotateMarkdownTree(child, annotations);
  }
}

function AnnotatedMarkdown({
  content,
  annotations,
  invert,
}: {
  content: string;
  annotations: PrivacyAnnotation[];
  invert?: boolean;
}) {
  const sortedAnnotations = [...annotations].sort((left, right) => left.start - right.start);
  const rehypePrivacyPlugin = () => {
    return (tree: MarkdownNode) => {
      annotateMarkdownTree(tree, sortedAnnotations);
    };
  };

  return (
    <TooltipProvider delayDuration={120}>
      <div className={cn('prose max-w-none break-words text-current', invert ? 'prose-invert' : 'dark:prose-invert')}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypePrivacyPlugin]}
          components={{
            span({ node, className, children, ...props }) {
              const rawIndex = node?.properties?.dataPrivacyIndex;
              const annotationIndex = typeof rawIndex === 'string' ? Number(rawIndex) : Number(rawIndex);
              const annotation = Number.isInteger(annotationIndex) ? sortedAnnotations[annotationIndex] : undefined;

              if (!annotation) {
                return (
                  <span className={className} {...props}>
                    {children}
                  </span>
                );
              }

              const extraAliases = annotation.aliases.filter((alias) => alias !== annotation.canonical);
              return (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span
                      className={cn(
                        'rounded-[0.22rem] bg-secondary/75 px-1 py-0.5 text-inherit shadow-[inset_0_-0.14rem_0_rgba(61,57,41,0.12)] transition-colors hover:bg-secondary/90',
                        className,
                      )}
                      {...props}
                    >
                      {children}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent className="max-w-xs rounded-2xl px-3 py-2">
                    <div className="space-y-1.5">
                      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                        Privacy-Protected Entity
                      </div>
                      <div className="text-sm font-medium text-foreground">{annotation.canonical}</div>
                      <div className="text-xs text-muted-foreground">
                        {formatEntityLabel(annotation.entity_type)} · {annotation.placeholder}
                      </div>
                      {extraAliases.length > 0 && (
                        <div className="text-xs text-muted-foreground">
                          Aliases: {extraAliases.join(', ')}
                        </div>
                      )}
                      {annotation.value !== null && annotation.value !== undefined && (
                        <div className="text-xs text-muted-foreground">
                          Normalized value: {String(annotation.value)}
                        </div>
                      )}
                    </div>
                  </TooltipContent>
                </Tooltip>
              );
            },
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    </TooltipProvider>
  );
}

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

function formatEntityLabel(value: string) {
  return value.replaceAll('_', ' ');
}

function privacySeverityClasses(severity: PrivacySummary['severity']) {
  if (severity === 'high') {
    return 'border-rose-200 bg-rose-50 text-rose-700';
  }
  if (severity === 'medium') {
    return 'border-amber-200 bg-amber-50 text-amber-700';
  }
  return 'border-emerald-200 bg-emerald-50 text-emerald-700';
}

function PrivacyPanel({
  open,
  onToggle,
  snapshot,
}: {
  open: boolean;
  onToggle: () => void;
  snapshot: PrivacySnapshot;
}) {
  return (
    <aside
      className={cn(
        'shrink-0 border-t border-border/60 bg-background/70 backdrop-blur-xl transition-all duration-200 lg:border-l lg:border-t-0',
        open ? 'flex max-h-[38vh] w-full flex-col lg:max-h-none lg:w-[360px]' : 'hidden lg:flex lg:w-[76px] lg:flex-col'
      )}
    >
      <div
        className={cn(
          'flex items-center justify-between gap-3 px-4 py-4',
          !open && 'h-full flex-col justify-start px-2 py-5'
        )}
      >
        {open ? (
          <>
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <Shield className="h-4 w-4 text-muted-foreground" />
                <span>Privacy Entities</span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {snapshot.total_entities > 0
                  ? `${snapshot.total_entities} entities accumulated in this chat session`
                  : 'No privacy entities detected in this chat session yet.'}
              </p>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-9 w-9 rounded-xl"
              onClick={onToggle}
              aria-label="Collapse privacy panel"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </>
        ) : (
          <>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-10 w-10 rounded-xl"
              onClick={onToggle}
              aria-label="Expand privacy panel"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <div className="text-center text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground [writing-mode:vertical-rl]">
              Privacy Panel
            </div>
          </>
        )}
      </div>

      {open && (
        <ScrollArea className="min-h-0 flex-1 px-4 pb-4">
          <div className="space-y-4 pb-2">
            {snapshot.entity_counts.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {snapshot.entity_counts.map((summary) => (
                  <div
                    key={`${summary.entity_type}-${summary.severity}`}
                    className={cn(
                      'rounded-md border px-3 py-1 text-[11px] font-medium uppercase tracking-[0.16em]',
                      privacySeverityClasses(summary.severity)
                    )}
                  >
                    {formatEntityLabel(summary.entity_type)} x{summary.count}
                  </div>
                ))}
              </div>
            )}

            {snapshot.entities.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-border/80 bg-card/70 px-4 py-5 text-sm text-muted-foreground">
                Detected entities will appear here after Cloakbot finishes a response.
              </div>
            ) : (
              snapshot.entities.map((entity) => {
                const extraAliases = entity.aliases.filter((alias) => alias !== entity.canonical);
                return (
                  <div
                    key={entity.placeholder}
                    className="rounded-2xl border border-border/70 bg-card/85 p-4 shadow-sm"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-semibold text-foreground">
                          {entity.canonical}
                        </div>
                        <div className="mt-1 text-xs text-muted-foreground">{entity.placeholder}</div>
                      </div>
                      <div
                        className={cn(
                          'shrink-0 rounded-md border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em]',
                          privacySeverityClasses(entity.severity)
                        )}
                      >
                        {formatEntityLabel(entity.entity_type)}
                      </div>
                    </div>

                    {extraAliases.length > 0 && (
                      <div className="mt-3">
                        <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                          Aliases
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {extraAliases.map((alias) => (
                            <span
                              key={`${entity.placeholder}-${alias}`}
                              className="rounded-md bg-secondary px-2.5 py-1 text-xs text-secondary-foreground"
                            >
                              {alias}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {entity.value !== null && entity.value !== undefined && (
                      <div className="mt-3 text-xs text-muted-foreground">
                        Normalized value: <span className="font-medium text-foreground">{String(entity.value)}</span>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </ScrollArea>
      )}
    </aside>
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
  const [privacyPanelOpen, setPrivacyPanelOpen] = useState(
    () => typeof window !== 'undefined' ? window.innerWidth >= 1024 : true
  );
  const [privacySnapshot, setPrivacySnapshot] = useState<PrivacySnapshot>(emptyPrivacySnapshot);
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
        setMessages((prev) => [
          ...prev,
          {
            id: Date.now().toString(),
            role: 'assistant',
            content: data.content,
            privacyAnnotations: (data.privacyAnnotations as PrivacyAnnotation[] | undefined) ?? [],
          },
        ]);
        if (data.privacy) {
          setPrivacySnapshot(data.privacy as PrivacySnapshot);
        }
      } else if (data.type === 'assistant_delta') {
        setMessages((prev) => {
          const newMessages = [...prev];
          const lastMsg = newMessages[newMessages.length - 1];
          if (lastMsg && lastMsg.role === 'assistant') {
            lastMsg.content += data.content;
            return newMessages;
          }
          return [
            ...newMessages,
            {
              id: Date.now().toString(),
              role: 'assistant',
              content: data.content,
              privacyAnnotations: [],
            },
          ];
        });
      } else if (data.type === 'assistant_done') {
        if (data.privacyAnnotations) {
          setMessages((prev) => {
            const newMessages = [...prev];
            const lastMsg = newMessages[newMessages.length - 1];
            if (lastMsg && lastMsg.role === 'assistant') {
              lastMsg.privacyAnnotations = data.privacyAnnotations as PrivacyAnnotation[];
            }
            return newMessages;
          });
        }
        if (data.privacy) {
          setPrivacySnapshot(data.privacy as PrivacySnapshot);
        }
      } else if (data.type === 'privacy_snapshot') {
        setPrivacySnapshot((data.data as PrivacySnapshot) ?? emptyPrivacySnapshot);
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
    <div className="flex min-h-0 flex-1 flex-col bg-transparent lg:flex-row">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
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
                    <AnnotatedMarkdown
                      content={msg.content}
                      annotations={msg.privacyAnnotations ?? []}
                      invert={msg.role === 'user'}
                    />
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

      <PrivacyPanel
        open={privacyPanelOpen}
        onToggle={() => setPrivacyPanelOpen((prev) => !prev)}
        snapshot={privacySnapshot}
      />
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
