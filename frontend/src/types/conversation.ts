export type ConversationSource = 'dashboard' | 'workspace';

export interface Conversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
  lastMessagePreview: string;
}

export interface ConversationListResp {
  list: Conversation[];
  total: number;
  page: number;
  pageSize: number;
}
