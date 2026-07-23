import { createContext, useContext } from "react";

import type { CompanionContext as CompanionContextValue } from "../../types/companion";

export type CompanionContextState = {
  activeContext: CompanionContextValue | null;
  isOpen: boolean;
  setContext: (context: CompanionContextValue) => void;
  clearContext: (subjectId?: string) => void;
  open: () => void;
  close: () => void;
};

export const CompanionContext = createContext<CompanionContextState | null>(null);

export function useCompanion() {
  const value = useContext(CompanionContext);
  if (!value) throw new Error("useCompanion must be used inside CompanionProvider");
  return value;
}

export function useOptionalCompanion() {
  return useContext(CompanionContext);
}
