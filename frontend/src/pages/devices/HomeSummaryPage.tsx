import { useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApplianceIcon } from '../../components/appliances/ApplianceIcons';
import { PageHero } from '../../components/art/PageHero';
import { RoomIcon } from '../../components/ui/RoomIcon';
import { useInventory } from '../../hooks/useInventory';
import { ArrowIcon, BoltIcon, EditIcon, InfoIcon } from '../../components/ui/icons';
import { groupOf } from '../../utils/applianceGroups';
import './devices.css';

/** "Your home at a glance": what has been added, by type and by room. */
export function HomeSummaryPage() {
  const navigate = useNavigate();
  const { rooms, inventory, totalQuantity, totalConfiguredRatedWatts } = useInventory();

  const types = useMemo(() => {
    const map = new Map<string, { icon: string; label: string; count: number }>();
    for (const item of inventory) {
      const g = groupOf(item.iconType);
      const cur = map.get(g.key) ?? { icon: item.iconType, label: g.plural, count: 0 };
      cur.count += item.quantity;
      map.set(g.key, cur);
    }
    return [...map.values()].sort((a, b) => b.count - a.count).slice(0, 5);
  }, [inventory]);

  const byRoom = useMemo(
    () =>
      rooms.map((room) => {
        const items = inventory.filter((i) => i.roomId === room.id);
        const groups = new Map<string, { icon: string; count: number }>();
        for (const it of items) {
          const g = groupOf(it.iconType);
          const cur = groups.get(g.key) ?? { icon: it.iconType, count: 0 };
          cur.count += it.quantity;
          groups.set(g.key, cur);
        }
        return { room, groups: [...groups.values()], total: items.reduce((s, i) => s + i.quantity, 0) };
      }),
    [rooms, inventory]
  );

  return (
    <div className="page">
      <PageHero art="story" eyebrow="Review" title={<>Your home<br />at a glance</>} subtitle="Here’s a summary of the appliances you’ve added." />

      <section className="card" aria-label="Total appliances">
        <div className="card__head">
          <div>
            <h2 className="card__title">Total appliances</h2>
            <p className="summary__total">{totalQuantity}</p>
          </div>
          <Link to="/devices" className="btn btn--soft btn--small"><EditIcon /> Edit</Link>
        </div>
        {types.length > 0 && (
          <div className="type-strip">
            {types.map((t) => (
              <div key={t.label} className="type-strip__item">
                <ApplianceIcon type={t.icon} size={34} />
                <b>{t.count}</b>
                <span>{t.label}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="card" aria-label="By room">
        <div className="card__head">
          <h2 className="card__title">By room</h2>
          <Link to="/devices/rooms" className="btn btn--soft btn--small"><EditIcon /> Edit</Link>
        </div>
        <div className="list">
          {byRoom.map(({ room, groups, total }) => (
            <div key={room.id} className="room-row">
              <span className="room-row__name"><RoomIcon name={room.name} size={24} /> {room.name}</span>
              <span className="room-row__chips">
                {groups.length === 0 ? <i>–</i> : groups.map((g) => (
                  <span key={g.icon} className="room-row__chip"><ApplianceIcon type={g.icon} size={18} />{g.count}</span>
                ))}
              </span>
              <span className="room-row__total">{total}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="load-card" aria-label="Estimated total load">
        <span className="load-card__icon"><BoltIcon size={26} /></span>
        <span>
          <span className="load-card__label">Estimated total load <InfoIcon /></span>
          <b className="load-card__value">{totalConfiguredRatedWatts.toLocaleString('en-IN')} W</b>
          <span className="load-card__hint">Based on standard wattage values.</span>
        </span>
      </section>

      <button type="button" className="btn btn--primary page__cta" onClick={() => navigate('/bill')}>
        Continue to add your bill
        <span className="btn__arrow"><ArrowIcon /></span>
      </button>
    </div>
  );
}
