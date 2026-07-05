import { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from '@/context/auth-context';
import { ChatProvider } from '@/context/chat-context';
import { WsStatusProvider } from '@/context/ws-context';
import { AppLayout } from '@/components/layout/app-layout';
import { LandingPage } from '@/pages/landing';
import { LoginPage } from '@/pages/login';
import { RegisterPage } from '@/pages/register';
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
import { KnowledgePage } from '@/pages/knowledge';
import { TemplatesPage } from '@/pages/templates';
import { SettingsPage } from '@/pages/settings';
import { SettingsModelsPage } from '@/pages/settings-models';
import { SettingsPlatformsPage } from '@/pages/settings-platforms';
import { SettingsSystemPage } from '@/pages/settings-system';
import { StatsPage } from '@/pages/stats';
import { ExpertListPage } from '@/pages/experts';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

/* ── Route guard: redirect to /login if not authenticated ────── */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

/* ── Landing / auth routing ──────────────────────────────────── */
function AppRoutes() {
  const { isAuthenticated } = useAuth();
  const [landed, setLanded] = useState(() => {
    // Skip landing if already logged in
    return isAuthenticated;
  });

  if (!landed) {
    return <LandingPage onEnter={() => setLanded(true)} />;
  }

  return (
    <Routes>
      {/* Public routes — always accessible, never intercepted by RequireAuth */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Protected routes — RequireAuth redirects to /login if unauthenticated */}
      <Route element={<RequireAuth><WsStatusProvider><ChatProvider><AppLayout /></ChatProvider></WsStatusProvider></RequireAuth>}>
        <Route index element={<Navigate to="/chat" replace />} />

        {/* Chat */}
        <Route path="chat" element={<ChatPage />} />
        <Route path="chat/:sessionId" element={<ChatPage />} />
        <Route path="experts" element={<ExpertListPage />} />
        <Route path="experts/:expertId/chat" element={<ChatPage />} />
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

        {/* Stats */}
        <Route path="stats" element={<StatsPage />} />

        {/* Knowledge */}
        <Route path="knowledge" element={<KnowledgePage />} />

        {/* Templates */}
        <Route path="templates" element={<TemplatesPage />} />

        {/* Experts */}
        <Route path="experts" element={<ExpertListPage />} />

        {/* Settings */}
        <Route path="settings" element={<SettingsPage />}>
          <Route index element={<Navigate to="models" replace />} />
          <Route path="models" element={<SettingsModelsPage />} />
          <Route path="platforms" element={<SettingsPlatformsPage />} />
          <Route path="system" element={<SettingsSystemPage />} />
        </Route>
      </Route>

      {/* Catch-all: authenticated → /chat, unauthenticated → /login */}
      <Route path="*" element={<Navigate to={isAuthenticated ? "/chat" : "/login"} replace />} />
    </Routes>
  );
}

function AppContent() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
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
