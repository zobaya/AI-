import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import GlobalDialogs from '@/components/GlobalDialogs'

export default function AppLayout() {
  return (
    <div className="flex h-screen" style={{ background: 'var(--bg)' }}>
      <Sidebar />
      <main className="flex-1 overflow-hidden min-w-0">
        <Outlet />
      </main>
      <GlobalDialogs />
    </div>
  )
}
