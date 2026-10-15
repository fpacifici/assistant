/**
 * Ask AI (`/ask?thread=<id>`): questions answered by the AI agent from the
 * user's notes. The open thread lives in the URL; `thread=new` (or none, on
 * desktop) is a new chat.
 *
 * Desktop: the app header above a thread sidebar and the conversation.
 * Mobile: the thread list at `/ask`, and a full-screen conversation once a
 * thread (or a new chat) is open.
 */

import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router';
import { fetchAskStatus } from '../api/ask';
import AskConversation from '../components/AskConversation';
import AskThreadList from '../components/AskThreadList';
import DesktopHeader from '../components/DesktopHeader';
import MobileTopBar from '../components/MobileTopBar';
import { useLayoutMode } from '../layout/LayoutModeContext';

export default function AskPage() {
  const mode = useLayoutMode();
  const isMobile = mode === 'mobile';
  const [searchParams, setSearchParams] = useSearchParams();
  const param = searchParams.get('thread');
  const threadId = param && param !== 'new' ? param : null;

  const { data: status, isLoading } = useQuery({
    queryKey: ['ask', 'status'],
    queryFn: fetchAskStatus,
    staleTime: Infinity,
    retry: false,
  });

  const openThread = (id: string) => setSearchParams({ thread: id }, { replace: true });
  const closeThread = () => setSearchParams({}, { replace: true });
  // Remount per thread so a switch drops the previous answer in progress.
  const conversation = (
    <AskConversation key={threadId ?? 'new'} threadId={threadId} onThreadCreated={openThread} />
  );

  let body: React.ReactNode;
  if (isLoading) {
    body = <p className="search-status">Loading…</p>;
  } else if (!status?.enabled) {
    body = <p className="search-status">Ask AI is not available on this server.</p>;
  } else if (isMobile) {
    body = param ? conversation : <AskThreadList activeId={null} onActiveDeleted={closeThread} />;
  } else {
    body = (
      <div className="ask-layout">
        <AskThreadList activeId={threadId} onActiveDeleted={closeThread} />
        {conversation}
      </div>
    );
  }

  return (
    <div className="app-shell" data-layout={mode}>
      {isMobile ? (
        <MobileTopBar title="Ask AI" backTo={param ? '/ask' : '/notebooks'} />
      ) : (
        <DesktopHeader />
      )}
      <main className="ask-page">{body}</main>
    </div>
  );
}
