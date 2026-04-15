import { useEffect, useState } from 'react';
import { Button, Empty, Modal, Skeleton, Tooltip } from 'antd';
import { PlusOutlined, DeleteOutlined, MessageOutlined, LoadingOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useConversationStore } from '@/store/conversationStore';
import { useWorkspaceStore } from '@/store/workspaceStore';
import type { Conversation, ConversationSource } from '@/types/conversation';
import styles from './ConversationList.module.css';

function SourceBadge({ source }: { source: ConversationSource | undefined }) {
  if (!source) return null;
  return (
    <span className={`${styles.badge} ${source === 'dashboard' ? styles.badgeDashboard : styles.badgeWorkspace}`}>
      {source === 'dashboard' ? '网络级' : '用户级'}
    </span>
  );
}

function formatTime(iso: string) {
  const d = dayjs(iso);
  if (d.isSame(dayjs(), 'day')) return d.format('HH:mm');
  if (d.isSame(dayjs().subtract(1, 'day'), 'day')) return '昨天';
  return d.format('MM-DD');
}

function ConversationList() {
  const { list, loading, fetch, create, remove, sources } = useConversationStore();
  const openConversation = useWorkspaceStore((s) => s.openConversation);
  const streamingConvIds = useWorkspaceStore((s) => s.streamingConvIds);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    fetch();
  }, [fetch]);

  const handleCreate = async () => {
    if (creating) return;
    setCreating(true);
    try {
      const conv = await create();
      openConversation(conv.id);
    } finally {
      setCreating(false);
    }
  };

  const handleClick = (conv: Conversation) => {
    openConversation(conv.id);
  };

  const handleDelete = (e: React.MouseEvent, conv: Conversation) => {
    e.stopPropagation();
    Modal.confirm({
      title: '确认删除该会话？',
      content: `「${conv.title}」将被永久删除`,
      okText: '删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: () => remove(conv.id),
    });
  };

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <h2 className={styles.title}>会话列表</h2>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={handleCreate}
          loading={creating}
          size="small"
        >
          新建对话
        </Button>
      </header>

      <div className={styles.scrollArea}>
        {loading && list.length === 0 ? (
          <div className={styles.skeletonWrap}>
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} active paragraph={{ rows: 1 }} />
            ))}
          </div>
        ) : list.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={<span style={{ color: '#6b7280' }}>暂无会话</span>}
            style={{ marginTop: 80 }}
          >
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
              新建第一个对话
            </Button>
          </Empty>
        ) : (
          list.map((conv) => (
            <div key={conv.id} className={styles.item} onClick={() => handleClick(conv)}>
              <div className={styles.itemHeader}>
                <div className={styles.itemTitle}>
                  {streamingConvIds.has(conv.id)
                    ? <LoadingOutlined className={styles.itemIcon} spin />
                    : <MessageOutlined className={styles.itemIcon} />
                  }
                  <span>{conv.title}</span>
                  <SourceBadge source={sources[conv.id]} />
                </div>
                <span className={styles.itemTime}>{formatTime(conv.updatedAt)}</span>
              </div>
              <div className={styles.itemPreview}>{conv.lastMessagePreview || '（暂无消息）'}</div>
              <Tooltip title="删除会话">
                <button
                  type="button"
                  className={styles.deleteBtn}
                  onClick={(e) => handleDelete(e, conv)}
                  aria-label="删除"
                >
                  <DeleteOutlined />
                </button>
              </Tooltip>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default ConversationList;
