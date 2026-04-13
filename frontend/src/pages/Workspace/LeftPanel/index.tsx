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
  const openConversation = useWorkspaceStore((s) => s.openConversation);
  const createConversation = useConversationStore((s) => s.create);

  // 从 Dashboard 跳转过来时，自动新建一个对话并切换到 chat 视图
  useEffect(() => {
    if (!prefillMessage) return;
    (async () => {
      const conv = await createConversation('新对话');
      openConversation(conv.id);
    })();
  // 只在 prefillMessage 首次有值时触发
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefillMessage]);

  return (
    <aside className={styles.leftPanel}>
      {leftView === 'list' ? <ConversationList /> : <ChatView prefillMessage={prefillMessage} />}
    </aside>
  );
}

export default LeftPanel;
