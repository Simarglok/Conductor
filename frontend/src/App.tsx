import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './lib/auth';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import AppShell from './pages/AppShell';
import ProjectListPage from './pages/ProjectListPage';
import PipelinePage from './pages/PipelinePage';
import DevPage from './pages/DevPage';
import GitPage from './pages/GitPage';
import SettingsPage from './pages/SettingsPage';
import AdminPage from './pages/AdminPage';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isAuthLoading } = useAuth();
  if (isAuthLoading) return <div className="min-h-screen flex items-center justify-center bg-[#0f1117]"><p className="text-gray-400">Loading…</p></div>;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/" element={<ProtectedRoute><AppShell /></ProtectedRoute>}>
            <Route index element={<Navigate to="/projects" replace />} />
            <Route path="projects" element={<ProjectListPage />} />
            <Route path="projects/:slug/pipeline" element={<PipelinePage />} />
            <Route path="projects/:slug/dev" element={<DevPage />} />
            <Route path="projects/:slug/git" element={<GitPage />} />
            <Route path="projects/:slug/settings" element={<SettingsPage />} />
            <Route path="admin" element={<AdminPage />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}