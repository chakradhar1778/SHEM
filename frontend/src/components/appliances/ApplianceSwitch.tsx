import { RelayToggle } from './RelayToggle';
import { SimToggle } from './SimToggle';

/** The right on/off switch for an appliance: the physical relay, or the simulator when it has no relay. */
export function ApplianceSwitch({ id, name, relayChannel }: { id: string; name: string; relayChannel?: number | null }) {
  return relayChannel != null ? <RelayToggle applianceName={name} channel={relayChannel} /> : <SimToggle applianceId={id} applianceName={name} />;
}
