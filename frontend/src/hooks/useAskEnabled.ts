import { useQuery } from '@tanstack/react-query';
import { fetchAskStatus } from '../api/ask';

/** Whether the server has AI enabled; false while unknown or on error. */
export function useAskEnabled(): boolean {
  const { data } = useQuery({
    queryKey: ['ask', 'status'],
    queryFn: fetchAskStatus,
    staleTime: Infinity,
    retry: false,
  });
  return data?.enabled ?? false;
}
