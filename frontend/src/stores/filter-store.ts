import { create } from "zustand";

interface FilterStore {
  symbolKind: string;
  filePath: string;
  searchQuery: string;
  setSymbolKind: (kind: string) => void;
  setFilePath: (path: string) => void;
  setSearchQuery: (q: string) => void;
  reset: () => void;
}

export const useFilterStore = create<FilterStore>()((set) => ({
  symbolKind: "",
  filePath: "",
  searchQuery: "",
  setSymbolKind: (kind) => set({ symbolKind: kind }),
  setFilePath: (path) => set({ filePath: path }),
  setSearchQuery: (q) => set({ searchQuery: q }),
  reset: () => set({ symbolKind: "", filePath: "", searchQuery: "" }),
}));
