import { useEffect } from 'react';
import { useWorkspaceStore } from '@/store/workspaceStore';
import { useConversationStore } from '@/store/conversationStore';
import ConversationList from './ConversationList';
import ChatView from './ChatView';
import styles from './LeftPanel.module.css';

interface Props {
  prefillMessage?: string;
}

function LeftPanel({ prefillMessage }: Props) {
  const leftView = useWorkspaceStore((s) => s.leftView);
  const setLeftView = useWorkspaceStore((s) => s.setLeftView);
  const setActiveConversation = useWorkspaceStore((s) => s.setActiveConversation);
  const createConversation = useConversationStore((s) => s.create);

  // 从 Dashboard 跳转过来时，立即切到 chat 视图（避免闪列表），再异步建会话
  useEffect(() => {
    if (!prefillMessage) return;
    setLeftView('chat'); // 同步切视图，消除闪烁
    (async () => {
      const conv = await createConversation('新对话');
      setActiveConversation(conv.id);
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefillMessage]);

  return (
    <aside className={styles.leftPanel}>
      {leftView === 'list' ? <ConversationList /> : <ChatView prefillMessage={prefillMessage} />}
    </aside>
  );
}

export default LeftPanel;
