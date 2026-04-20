import { AppShell } from '@/app/layout/AppShell'
import { ChatPage } from '@/pages/chat/ChatPage'
import { ConfigPage } from '@/pages/config/ConfigPage'

export default function App() {
  return <AppShell tabContent={{ chat: <ChatPage />, config: <ConfigPage /> }} />
}
