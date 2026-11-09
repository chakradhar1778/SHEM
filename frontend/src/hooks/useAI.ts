import { useContext } from 'react';
import { AIContext, type AIContextType } from '../context/aiContextDef';

/** SHEM AI chat, conflicts and daily briefing. */
export function useAI(): AIContextType {
  const ctx = useContext(AIContext);
  if (!ctx) throw new Error('useAI must be used within an AIProvider');
  return ctx;
}
