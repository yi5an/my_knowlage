import { type ReactNode, useCallback, useMemo, useState } from "react";

import type { CompanionContext as CompanionContextValue } from "../../types/companion";
import { CompanionContext } from "./companionContext";

export function CompanionProvider({
  children,
  initialContext,
}: {
  children: ReactNode;
  initialContext?: CompanionContextValue;
}) {
  const [activeContext, setActiveContext] = useState<CompanionContextValue | null>(initialContext ?? null);
  const [isOpen, setIsOpen] = useState(false);
  const setContext = useCallback((context: CompanionContextValue) => setActiveContext(context), []);
  const clearContext = useCallback((subjectId?: string) => {
    setActiveContext((current) => (subjectId && current?.subjectId !== subjectId ? current : null));
  }, []);
  const value = useMemo(
    () => ({
      activeContext,
      isOpen,
      setContext,
      clearContext,
      open: () => setIsOpen(true),
      close: () => setIsOpen(false),
    }),
    [activeContext, clearContext, isOpen, setContext],
  );
  return <CompanionContext.Provider value={value}>{children}</CompanionContext.Provider>;
}
