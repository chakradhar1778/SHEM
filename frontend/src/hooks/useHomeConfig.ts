import { useContext } from 'react';
import { HomeContext } from '../context/homeContextDef';
import type { HomeContextType } from '../context/homeContextDef';

export function useHomeConfig(): HomeContextType {
  const ctx = useContext(HomeContext);
  if (!ctx) {
    throw new Error('useHomeConfig must be used within a HomeProvider');
  }
  return ctx;
}
