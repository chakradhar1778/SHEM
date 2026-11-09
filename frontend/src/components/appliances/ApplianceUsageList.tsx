import { Link } from 'react-router-dom';
import type { ApplianceUsage } from '../../api/types';
import { useLiveData } from '../../hooks/useLiveData';
import { formatKWh, formatWatts } from '../../utils/simFormat';
import { ApplianceIcon } from './ApplianceIcons';
import { SourceTag } from './SourceTag';
import './Simulation.css';

interface Props {
  items: ApplianceUsage[];
  /** Show each appliance's live power next to its energy (dashboard / today). */
  showLive?: boolean;
  limit?: number;
  /** Link rows to the appliance edit screen. */
  linkToEdit?: boolean;
}

/** Clear per-appliance breakdown: energy, share, cost and source (Metered / Simulated). */
export function ApplianceUsageList({ items, showLive = false, limit, linkToEdit = true }: Props) {
  const { simById, relay, meteredPowerW, isLive } = useLiveData();
  const shown = limit ? items.slice(0, limit) : items;
  const max = Math.max(1e-9, ...shown.map((i) => i.kwh));

  return (
    <div className="usage-list">
      {shown.map((a) => {
        const sim = a.source === 'simulated';
        const liveSim = sim ? simById[a.applianceId] : undefined;
        // The metered circuit's live power is the PZEM reading itself (only while the meter is live).
        const liveW = sim ? liveSim?.powerW : isLive ? meteredPowerW : undefined;
        const on = sim ? liveSim?.state === 'ON' : relay?.commandedState === 'ON' || meteredPowerW > 1;
        const sub = [
          a.roomName,
          `${Math.round(a.percentage)}%`,
          a.onHours != null ? `on ${a.onHours < 1 ? `${Math.round(a.onHours * 60)} min` : `${a.onHours.toFixed(1)} h`}` : null,
          a.peakHourLabel ? `peak ${a.peakHourLabel}` : null,
        ].filter(Boolean).join(' · ');
        const body = (
          <>
            <span className="usage-row__icon"><ApplianceIcon type={a.iconType ?? 'bulb'} size={28} /></span>
            <span className="usage-row__body">
              <span className="usage-row__top">
                <span className="usage-row__name">{a.name}</span>
                <SourceTag source={a.source} compact />
              </span>
              <span className="usage-row__track"><span className={sim ? 'is-sim' : ''} style={{ width: `${Math.max(3, (a.kwh / max) * 100)}%` }} /></span>
              <span className="usage-row__sub">{sub}</span>
            </span>
            <span className="usage-row__val">
              {formatKWh(a.kwh)} kWh
              <span>₹{a.costINR.toFixed(a.costINR < 10 ? 2 : 0)}</span>
              {showLive && liveW != null && <span className={on ? 'is-on' : ''}>{on ? formatWatts(liveW) : 'Off'}</span>}
            </span>
          </>
        );
        const canLink = linkToEdit && a.applianceId !== 'metered-circuit';
        return canLink ? (
          <Link key={a.applianceId} to={`/devices/edit/${a.applianceId}`} className="usage-row" style={{ textDecoration: 'none' }}>{body}</Link>
        ) : (
          <div key={a.applianceId} className="usage-row">{body}</div>
        );
      })}
    </div>
  );
}
