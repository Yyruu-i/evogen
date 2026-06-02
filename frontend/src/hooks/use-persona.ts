import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { personaApi } from '@/lib/api';
import type { PersonaAttributes } from '@/types';

export function usePersona() {
  return useQuery<{ attributes: PersonaAttributes }>({
    queryKey: ['persona'],
    queryFn: () => personaApi.getAttributes(),
    staleTime: 30000,
  });
}

export function useUpdatePersona() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (attrs: Record<string, unknown>) => personaApi.updateAttributes(attrs),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['persona'] }),
  });
}

export function useUpdatePersonaAttribute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: unknown }) =>
      personaApi.updateAttribute(key, value),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['persona'] }),
  });
}
