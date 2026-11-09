import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useLiveData } from '../hooks/useLiveData';
import { useInventory } from '../hooks/useInventory';
import { LiveSpeedometerGauge } from '../components/live/LiveSpeedometerGauge';
import { ApplianceIcon } from '../components/appliances/ApplianceIcons';
import { ApplianceRelayControl } from '../components/appliances/ApplianceRelayControl';
import { SimToggle } from '../components/appliances/SimToggle';
import { SourceTag } from '../components/appliances/SourceTag';
import { PageHero } from '../components/art/PageHero';
import { BoltIcon, ChevronRight } from '../components/ui/icons';
import { formatAge, formatNumber } from '../utils/liveFormat';
import { formatKWh, formatWatts } from '../utils/simFormat';
import './LiveUsagePage.css';

const GAUGE_STEPS = [100, 250, 500, 1000, 2000, 3000, 5000, 10000, 25000];
const gaugeScale = (maxSeenW: number) => GAUGE_STEPS.find((s) => s >= maxSeenW * 1.2) ?? 25000;

/** Live Usage: whole-home power (metered circuit + simulated appliances) and every switchable appliance. */
export function LiveUsagePage() {
  const { latest, isLive, latestAgeSeconds, relay, streamStatus, sim, simById, homePowerW, meteredPowerW, homePoints, homeLive } = useLiveData();
  const { inventory, rooms } = useInventory();

  const scale = useMemo(
    () => gaugeScale(Math.max(homePowerW ?? 0, ...homePoints.map((p) => p.powerW), 0)),
    [homePowerW, homePoints]
  );
  const relayItems = inventory.filter((i) => i.relayChannel != null);
  const simItems = inventory
    .filter((i) => i.relayChannel == null)
    .sort((a, b) => (simById[b.id]?.powerW ?? 0) - (simById[a.id]?.powerW ?? 0));
  const relayOn = relay?.commandedState === 'ON';
  const simOn = sim?.appliances.filter((a) => a.state === 'ON').length ?? 0;

  const status = isLive
    ? 'Live data'
    : homeLive
      ? 'Simulated live · meter offline'
      : latest
        ? `Last reading ${formatAge(latestAgeSeconds)}`
        : streamStatus === 'open'
          ? 'Waiting for meter'
          : 'Offline';

  return (
    <div className="page">
      <PageHero art="cottage" title="Live Usage" subtitle="Right now in your home">
        <span className={`status-pill ${homeLive ? 'is-live' : ''}`}><i /> {status}</span>
      </PageHero>

      <section className="card gauge-card" aria-label="Live power">
        <LiveSpeedometerGauge powerWatts={homePowerW} maxScaleWatts={scale} isLive={homeLive} />
        <p className="gauge-card__note">
          <BoltIcon size={16} />
          {simItems.length > 0 ? 'Whole home: metered circuit + simulated appliances' : 'Live power consumption of the metered circuit'}
        </p>
        {simItems.length > 0 && (
          <div className="gauge-split">
            <div><SourceTag source="metered" compact /><b>{isLive ? formatWatts(meteredPowerW) : '--'}</b><span>relay circuit</span></div>
            <div><SourceTag source="simulated" compact /><b>{formatWatts(sim?.totalPowerW ?? 0)}</b><span>{simOn} of {simItems.length} on</span></div>
          </div>
        )}
      </section>

      <section className="card" aria-label="Electrical readings">
        <div className="reading-strip">
          <div><b>{formatNumber(latest?.voltageV ?? sim?.voltageV, 0)}<small> V</small></b><span>Voltage</span></div>
          <div><b>{formatNumber(latest?.currentA, 2)}<small> A</small></b><span>Current (meter)</span></div>
          <div><b>{formatNumber(latest?.powerFactor, 2)}</b><span>Power factor</span></div>
        </div>
      </section>

      <section className="card" aria-label="Your appliances">
        <div className="card__head">
          <h2 className="card__title">Your appliances</h2>
          {homeLive && inventory.length > 0 && <span className="live-tag">Live</span>}
        </div>

        {inventory.length === 0 ? (
          <div className="empty">
            <BoltIcon size={26} />
            <span>
              <strong>No appliances yet.</strong>
              Add some in <Link to="/devices" className="inline-link">Devices</Link>: link one to the relay, the rest run as simulated devices.
            </span>
          </div>
        ) : (
          <div className="list">
            {relayItems.map((item) => (
              <div key={item.id} className="switch-item">
                <Link to={`/devices/edit/${item.id}`} className="row">
                  <span className="row__icon"><ApplianceIcon type={item.iconType} size={34} /></span>
                  <span className="row__body">
                    <span className="row__title">{item.name} <SourceTag source="metered" compact /></span>
                    <span className="row__sub">Relay {item.relayChannel}{isLive ? ` · ${formatWatts(meteredPowerW)} now` : ''}</span>
                  </span>
                  <span className={`state-pill ${relayOn ? 'is-on' : ''}`}>{relay?.commandedState ? (relayOn ? 'On' : 'Off') : '—'}</span>
                  <span className="row__end"><ChevronRight /></span>
                </Link>
                <ApplianceRelayControl applianceName={item.name} channel={item.relayChannel!} />
              </div>
            ))}
            {simItems.map((item) => {
              const live = simById[item.id];
              const room = rooms.find((r) => r.id === item.roomId)?.name;
              return (
                <div key={item.id} className="row sim-row">
                  <Link to={`/devices/edit/${item.id}`} className="device-row__link">
                    <span className="row__icon"><ApplianceIcon type={item.iconType} size={34} /></span>
                    <span className="row__body">
                      <span className="row__title">{item.name}{item.quantity > 1 ? ` × ${item.quantity}` : ''} <SourceTag source="simulated" compact /></span>
                      <span className="row__sub">{[room, live ? `${formatKWh(live.todayKWh)} kWh today` : null].filter(Boolean).join(' · ')}</span>
                    </span>
                  </Link>
                  <SimToggle applianceId={item.id} applianceName={item.name} />
                </div>
              );
            })}
          </div>
        )}
      </section>

      <Link to="/insights/daily" className="insight-link">
        <span className="insight-link__icon"><BoltIcon size={22} /></span>
        <span className="insight-link__text">
          <b>See today’s energy by hour</b>
          <span>Per-appliance and peak-hour breakdown</span>
        </span>
        <ChevronRight />
      </Link>
    </div>
  );
}
