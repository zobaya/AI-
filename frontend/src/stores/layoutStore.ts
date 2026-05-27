import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface LayoutState {
  chatSidebarCollapsed: boolean
  toggleChatSidebar: () => void
}

export const useLayoutStore = create<LayoutState>()(
  persist(
    (set) => ({
      chatSidebarCollapsed: false,
      toggleChatSidebar: () => set((s) => ({ chatSidebarCollapsed: !s.chatSidebarCollapsed })),
    }),
    { name: 'layout-preferences' }
  )
)
