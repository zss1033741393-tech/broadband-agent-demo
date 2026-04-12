import { get, post, patch, del } from './request';
import type { Conversation, ConversationListResp } from '@/types/conversation';

export function listConversations(params?: { page?: number; pageSize?: number }) {
  return get<ConversationListResp>('/conversations', params);
}

export function createConversation(title = '新对话') {
  return post<Conversation>('/conversations', { title });
}

export function updateConversationTitle(id: string, title: string) {
  return patch<null>(`/conversations/${id}`, { title });
}

export function deleteConversation(id: string) {
  return del<null>(`/conversations/${id}`);
}
