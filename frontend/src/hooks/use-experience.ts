import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { experienceApi } from '@/lib/api';
import type { TrajectoryListResponse, FeedbackListResponse, FeedbackRecord } from '@/types';

export function useTrajectories(params?: {
  limit?: number; offset?: number; with_feedback_only?: boolean; success?: boolean;
}) {
  return useQuery<TrajectoryListResponse>({
    queryKey: ['experience', 'trajectories', params],
    queryFn: () => experienceApi.listTrajectories(params),
    staleTime: 10000,
  });
}

export function useTrajectory(id: string) {
  return useQuery({
    queryKey: ['experience', 'trajectories', id],
    queryFn: () => experienceApi.getTrajectory(id),
    enabled: !!id,
  });
}

export function useFeedback(params?: { status?: string; limit?: number; offset?: number }) {
  return useQuery<FeedbackListResponse>({
    queryKey: ['experience', 'feedback', params],
    queryFn: () => experienceApi.listFeedback(params),
    staleTime: 10000,
  });
}

export function useAddFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (opt: { trajectory_id: string; rating: 'good' | 'neutral' | 'bad'; note?: string }) =>
      experienceApi.addFeedback(opt),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['experience'] });
    },
  });
}

export function useUpdateFeedbackStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: 'reviewed' | 'applied' | 'dismissed' }) =>
      experienceApi.updateFeedbackStatus(id, status),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['experience'] });
    },
  });
}
