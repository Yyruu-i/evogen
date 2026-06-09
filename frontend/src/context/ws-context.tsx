/* ═══════════════════════════════════════════════════════════
   EvoGen — WebSocket status context
   Shared between ChatPage (producer) and Sidebar (consumer).
   ═══════════════════════════════════════════════════════════ */

import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

export type WsStatus = 'connecting' | 'connected' | 'disconnected';

interface WsStatusContextValue {
  wsStatus: WsStatus;
  setWsStatus: (status: WsStatus) => void;
}

const WsStatusContext = createContext<WsStatusContextValue>({
  wsStatus: 'disconnected',
  setWsStatus: () => {},
});

export function WsStatusProvider({ children }: { children: ReactNode }) {
  const [wsStatus, setWsStatus] = useState<WsStatus>('disconnected');

  return (
    <WsStatusContext.Provider value={{ wsStatus, setWsStatus }}>
      {children}
    </WsStatusContext.Provider>
  );
}

export function useWsStatus() {
  const ctx = useContext(WsStatusContext);
  return ctx;
}
