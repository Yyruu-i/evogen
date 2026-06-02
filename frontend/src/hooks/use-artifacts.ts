import { useQuery } from '@tanstack/react-query';
import { artifactsApi } from '@/lib/api';
import type { ArtifactListResponse } from '@/types';

export function useArtifacts(params?: { type?: string; session_id?: string }) {
  return useQuery<ArtifactListResponse>({
    queryKey: ['artifacts', params],
    queryFn: () => artifactsApi.list(params),
    staleTime: 10000,
  });
}
