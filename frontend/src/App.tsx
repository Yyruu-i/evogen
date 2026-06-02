import { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ChatProvider } from '@/context/chat-context';
import { AppLayout } from '@/components/layout/app-layout';
import { LandingPage } from '@/pages/landing';
import { ChatPage } from '@/pages/chat';
import { MemoryPage } from '@/pages/memory';
import { MemoryListPage } from '@/pages/memory-list';
import { MemoryDetailPage } from '@/pages/memory-detail';
import { MemorySearchPage } from '@/pages/memory-search';
import { ExperiencePage } from '@/pages/experience';
import { ExperienceListPage } from '@/pages/experience-list';
import { ExperienceDetailPage } from '@/pages/experience-detail';
import { FeedbackQueuePage } from '@/pages/experience-feedback';
import { PersonaPage } from '@/pages/persona';
import { PersonaAttributesPage } from '@/pages/persona-attributes';
import { PersonaPreferencesPage } from '@/pages/persona-preferences';
import { PersonaSyncPage } from '@/pages/persona-sync';
import { SkillsPage } from '@/pages/skills';
import { SkillsLocalPage } from '@/pages/skills-local';
import { SkillsHubPage } from '@/pages/skills-hub';
import { SkillsDetailPage } from '@/pages/skills-detail';
import { ToolsPage } from '@/pages/tools';
import { SettingsPage } from '@/pages/settings';
import { SettingsModelsPage } from '@/pages/settings-models';
import { SettingsPlatformsPage } from '@/pages/settings-platforms';
import { SettingsSkillsPage } from '@/pages/settings-skills';
import { SettingsSystemPage } from '@/pages/settings-system';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function AppContent() {
  const [landed, setLanded] = useState(false);

  if (!landed) {
    return <LandingPage onEnter={() => setLanded(true)} />;
  }

  return (
    <Routes>
      <Route element={<ChatProvider><AppLayout /></ChatProvider>}>
        <Route index element={<Navigate to="/chat" replace />} />

        {/* Chat */}
        <Route path="chat" element={<ChatPage />} />
        <Route path="chat/:sessionId" element={<ChatPage />} />

        {/* Memory */}
        <Route path="memory" element={<MemoryPage />}>
          <Route index element={<Navigate to="list" replace />} />
          <Route path="list" element={<MemoryListPage />} />
          <Route path="search" element={<MemorySearchPage />} />
          <Route path=":factId" element={<MemoryDetailPage />} />
        </Route>

        {/* Experience */}
        <Route path="experience" element={<ExperiencePage />}>
          <Route index element={<Navigate to="list" replace />} />
          <Route path="list" element={<ExperienceListPage />} />
          <Route path="feedback" element={<FeedbackQueuePage />} />
          <Route path=":expId" element={<ExperienceDetailPage />} />
        </Route>

        {/* Persona */}
        <Route path="persona" element={<PersonaPage />}>
          <Route index element={<Navigate to="attributes" replace />} />
          <Route path="attributes" element={<PersonaAttributesPage />} />
          <Route path="preferences" element={<PersonaPreferencesPage />} />
          <Route path="sync" element={<PersonaSyncPage />} />
        </Route>

        {/* Skills */}
        <Route path="skills" element={<SkillsPage />}>
          <Route index element={<Navigate to="local" replace />} />
          <Route path="local" element={<SkillsLocalPage />} />
          <Route path="local/:skillId" element={<SkillsDetailPage />} />
          <Route path="hub" element={<SkillsHubPage />} />
        </Route>

        {/* Tools */}
        <Route path="tools" element={<ToolsPage />} />

        {/* Settings */}
        <Route path="settings" element={<SettingsPage />}>
          <Route index element={<Navigate to="models" replace />} />
          <Route path="models" element={<SettingsModelsPage />} />
          <Route path="platforms" element={<SettingsPlatformsPage />} />
          <Route path="skills" element={<SettingsSkillsPage />} />
          <Route path="system" element={<SettingsSystemPage />} />
        </Route>
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppContent />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
