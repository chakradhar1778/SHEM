import { Link } from 'react-router-dom';
import { ApplianceIcon } from '../../components/appliances/ApplianceIcons';
import { PageHero } from '../../components/art/PageHero';
import { ApplianceSwitch } from '../../components/appliances/ApplianceSwitch';
import { SourceTag } from '../../components/appliances/SourceTag';
import { RouteToast } from '../../components/ui/RouteToast';
import { useInventory } from '../../hooks/useInventory';
import { ChevronRight, PlusIcon } from '../../components/ui/icons';
import './devices.css';

/** Devices tab: everything already added, with Add device at the top. */
export function DevicesHomePage() {
  const { inventory, rooms, totalQuantity } = useInventory();

  return (
    <div className="page">
      <RouteToast />
      <PageHero art="villa" title={<>My<br />devices</>} subtitle="Track and manage the appliances in your home." />

      <section className="sheet" aria-label="My devices">
        <div className="devices-head">
          <div>
            <h2 className="card__title">My devices</h2>
            <p className="sheet__hint">
              {inventory.length === 0 ? 'Nothing added yet' : `${totalQuantity} ${totalQuantity === 1 ? 'device' : 'devices'} in your home`}
            </p>
          </div>
          <Link to="/devices/add" className="btn btn--primary btn--small" id="btn-add-device">
            <PlusIcon size={18} /> Add device
          </Link>
        </div>

        {inventory.length === 0 ? (
          <div className="empty">
            <ApplianceIcon type="fridge" size={34} />
            <span>
              <strong>No devices added yet.</strong>
              Add your first device to track and understand your energy usage.
            </span>
          </div>
        ) : (
          <div className="list">
            {inventory.map((item) => {
              const room = rooms.find((r) => r.id === item.roomId);
              return (
                <div key={item.id} className="row device-row">
                  <Link to={`/devices/edit/${item.id}`} className="device-row__link">
                    <span className="row__icon"><ApplianceIcon type={item.iconType} size={34} /></span>
                    <span className="row__body">
                      <span className="row__title">{item.name}{item.quantity > 1 ? ` × ${item.quantity}` : ''}</span>
                      <span className="row__sub">
                        <SourceTag source={item.relayChannel != null ? 'metered' : 'simulated'} compact />{' '}
                        {room?.name ?? 'No room'} · {item.ratedWatts} W{item.relayChannel != null ? ` · Relay ${item.relayChannel}` : ''}
                      </span>
                    </span>
                  </Link>
                  <ApplianceSwitch id={item.id} name={item.name} relayChannel={item.relayChannel} />
                </div>
              );
            })}
          </div>
        )}

        {inventory.length > 0 && (
          <Link to="/devices/summary" className="link-more devices-summary-link">View home summary <ChevronRight size={14} /></Link>
        )}
      </section>
    </div>
  );
}
