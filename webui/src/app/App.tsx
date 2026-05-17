import { AppShell } from '@/app/layout/AppShell'
import { ThemeProvider } from '@/app/theme/ThemeProvider'
import { RemoteViewProvider } from '@/features/chat/context/RemoteViewContext'
import { PrivacyStateProvider } from '@/features/privacy/context/PrivacyStateContext'
import { ChatPage } from '@/pages/chat/ChatPage'
import { ConfigPage } from '@/pages/config/ConfigPage'
import { SkillsPage } from '@/pages/skills/SkillsPage'

export default function App() {
  return (
    <ThemeProvider>
      <PrivacyStateProvider>
        <RemoteViewProvider>
          <AppShell tabContent={{ chat: <ChatPage />, config: <ConfigPage />, skills: <SkillsPage /> }} />
        </RemoteViewProvider>
      </PrivacyStateProvider>
    </ThemeProvider>
  )
}
