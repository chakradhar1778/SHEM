import { useContext } from 'react';
import { TargetContext, type TargetContextType } from '../context/targetContextDef';

/**
 * Hook to access the Energy Target state and operations.
 */
export function useTarget(): TargetContextType {
  const context = useContext(TargetContext);
  if (!context) {
    throw new Error('useTarget must be used within a TargetProvider');
  }
  return context;
}
