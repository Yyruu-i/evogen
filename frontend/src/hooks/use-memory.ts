import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { memoryApi } from '@/lib/api';
import type { MemoryFactListResponse, MemoryFact, ManualFactInput, FactUpdate, MemoryStats } from '@/types';

export function useMemory(params?: {
  layer?: string; type?: string; limit?: number; offset?: number; q?: string;
}) {
  return useQuery<MemoryFactListResponse>({
    queryKey: ['memory', params],
    queryFn: () => memoryApi.list(params),
    staleTime: 10000,
  });
}

export function useMemoryFact(id: string) {
  return useQuery<MemoryFact>({
    queryKey: ['memory', id],
    queryFn: () => memoryApi.get(id),
    enabled: !!id,
  });
}

export function useSearchMemory(query: string) {
  return useQuery<MemoryFactListResponse>({
    queryKey: ['memory', 'search', query],
    queryFn: () => memoryApi.list({ q: query, limit: 20 }),
    enabled: query.length > 0,
  });
}

export function useMemoryStats() {
  return useQuery<MemoryStats>({
    queryKey: ['memory', 'stats'],
    queryFn: () => memoryApi.stats(),
    staleTime: 30000,
  });
}

export function useCreateMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ManualFactInput) => memoryApi.create(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['memory'] }),
  });
}

export function useUpdateMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: FactUpdate }) =>
      memoryApi.update(id, updates),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['memory'] }),
  });
}

export function useDeleteMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => memoryApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['memory'] }),
  });
}
