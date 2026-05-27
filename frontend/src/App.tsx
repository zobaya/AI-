import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import Login from '@/pages/Login'
import Chat from '@/pages/Chat'
import Knowledge from '@/pages/Knowledge'
import ChunkDetail from '@/pages/ChunkDetail'
import Users from '@/pages/Users'
import Feedback from '@/pages/Feedback'
import Dashboard from '@/pages/Dashboard'
import Settings from '@/pages/Settings'
import AIMemory from '@/pages/AIMemory'
import Tags from '@/pages/Tags'
import AppLayout from '@/components/Layout/AppLayout'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />
}

function PublicRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  return isAuthenticated ? <Navigate to="/chat" replace /> : <>{children}</>
}

function AuthInitializer({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false)
  const initialize = useAuthStore((s) => s.initialize)

  useEffect(() => {
    initialize().finally(() => setReady(true))
  }, [initialize])

  if (!ready) {
    return (
      <div className="flex items-center justify-center h-screen" style={{ background: 'var(--bg)' }}>
        <div className="flex flex-col items-center gap-3">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center text-white font-bold text-lg"
            style={{ background: 'var(--primary)' }}
          >
            AI
          </div>
          <span className="text-sm" style={{ color: 'var(--text-muted)' }}>加载中...</span>
        </div>
      </div>
    )
  }

  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthInitializer>
        <Routes>
          <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <AppLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="/chat" replace />} />
            <Route path="chat" element={<Chat />} />
            <Route path="chat/:convId" element={<Chat />} />
            <Route path="knowledge" element={<Knowledge />} />
            <Route path="knowledge/:kbId/docs/:docId" element={<ChunkDetail />} />
            <Route path="admin/users" element={<Users />} />
            <Route path="admin/tags" element={<Tags />} />
            <Route path="admin/feedback" element={<Feedback />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="settings" element={<Settings />} />
            <Route path="settings/memory" element={<AIMemory />} />
          </Route>
        </Routes>
      </AuthInitializer>
    </BrowserRouter>
  )
}
