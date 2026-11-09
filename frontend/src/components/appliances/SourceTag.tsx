import type { UsageSource } from '../../api/types';
import './Simulation.css';

/**
 * Marks where an appliance's numbers come from: "Simulated" (no relay — realistic simulated device)
 * or "Metered" (the relay circuit measured by the PZEM meter).
 */
export function SourceTag({ source, compact = false }: { source: UsageSource | 'simulated' | 'metered'; compact?: boolean }) {
  const sim = source === 'simulated';
  return (
    <span
      className={`src-tag ${sim ? 'src-tag--sim' : 'src-tag--metered'} ${compact ? 'src-tag--compact' : ''}`}
      title={sim ? 'Simulated device: realistic power model, not physically metered' : 'Measured by the SHEM meter on the relay circuit'}
    >
      {sim ? 'Simulated' : 'Metered'}
    </span>
  );
}

export function SimTag({ compact }: { compact?: boolean }) {
  return <SourceTag source="simulated" compact={compact} />;
}
