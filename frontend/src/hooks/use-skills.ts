import { useQuery } from '@tanstack/react-query';
import { skillsApi } from '@/lib/api';
import type { SkillListResponse } from '@/types';

export function useSkills() {
  return useQuery<SkillListResponse>({
    queryKey: ['skills'],
    queryFn: () => skillsApi.list(),
    staleTime: 30000,
  });
}
