import { AppShell } from '@/app/layout/AppShell'
import { ThemeProvider } from '@/app/theme/ThemeProvider'
import { ChatPage } from '@/pages/chat/ChatPage'
import { ConfigPage } from '@/pages/config/ConfigPage'
import { SkillsPage } from '@/pages/skills/SkillsPage'

export default function App() {
  return (
    <ThemeProvider>
      <AppShell tabContent={{ chat: <ChatPage />, config: <ConfigPage />, skills: <SkillsPage /> }} />
    </ThemeProvider>
  )
}
