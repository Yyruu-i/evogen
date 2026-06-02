import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { sessionsApi } from '@/lib/api';
import type { SessionListResponse, MessageListResponse } from '@/types';

export function useSessions(params?: { limit?: number; offset?: number; source?: string }) {
  return useQuery<SessionListResponse>({
    queryKey: ['sessions', params],
    queryFn: () => sessionsApi.list(params),
    staleTime: 5000,
  });
}

export function useSession(id: string) {
  return useQuery({
    queryKey: ['sessions', id],
    queryFn: () => sessionsApi.get(id),
    enabled: !!id,
  });
}

export function useSessionMessages(sessionId: string) {
  return useQuery<MessageListResponse>({
    queryKey: ['sessions', sessionId, 'messages'],
    queryFn: () => sessionsApi.messages(sessionId),
    enabled: !!sessionId,
    staleTime: 5000,
  });
}

export function useDeleteSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => sessionsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sessions'] }),
  });
}
