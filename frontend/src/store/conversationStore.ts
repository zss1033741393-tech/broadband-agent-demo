import { create } from 'zustand';
import * as api from '@/api/conversations';
import type { Conversation, ConversationSource } from '@/types/conversation';

const SOURCES_KEY = 'conv_sources';

function loadSources(): Record<string, ConversationSource> {
  try {
    return JSON.parse(localStorage.getItem(SOURCES_KEY) ?? '{}');
  } catch {
    return {};
  }
}

function saveSources(sources: Record<string, ConversationSource>) {
  localStorage.setItem(SOURCES_KEY, JSON.stringify(sources));
}

interface ConversationState {
  list: Conversation[];
  loading: boolean;
  sources: Record<string, ConversationSource>;

  fetch: () => Promise<void>;
  create: (title?: string) => Promise<Conversation>;
  updateTitle: (id: string, title: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
  setSource: (id: string, source: ConversationSource) => void;
}

export const useConversationStore = create<ConversationState>((set, get) => ({
  list: [],
  loading: false,
  sources: loadSources(),

  fetch: async () => {
    set({ loading: true });
    try {
      const resp = await api.listConversations();
      set({ list: resp.list });
    } finally {
      set({ loading: false });
    }
  },

  create: async (title?: string) => {
    const conv = await api.createConversation(title);
    set({ list: [conv, ...get().list] });
    return conv;
  },

  updateTitle: async (id: string, title: string) => {
    await api.updateConversationTitle(id, title);
    set({
      list: get().list.map((c) => (c.id === id ? { ...c, title } : c)),
    });
  },

  remove: async (id: string) => {
    await api.deleteConversation(id);
    set({ list: get().list.filter((c) => c.id !== id) });
    const next = { ...get().sources };
    delete next[id];
    saveSources(next);
    set({ sources: next });
  },

  setSource: (id, source) => {
    const next = { ...get().sources, [id]: source };
    saveSources(next);
    set({ sources: next });
  },
}));
