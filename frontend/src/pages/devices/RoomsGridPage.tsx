import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { APPLIANCE_CATEGORIES } from '../../data/applianceCatalogue';
import { GRID_COLUMNS } from '../../utils/applianceGroups';
import { ApplianceIcon } from '../../components/appliances/ApplianceIcons';
import { PageHero } from '../../components/art/PageHero';
import { RoomIcon } from '../../components/ui/RoomIcon';
import { useInventory } from '../../hooks/useInventory';
import { ArrowIcon, ChevronDown, FileIcon, PlusIcon } from '../../components/ui/icons';
import './devices.css';

const CATALOGUE = new Map(APPLIANCE_CATEGORIES.flatMap((c) => c.items).map((i) => [i.id, i]));

/** Quick-add grid: tap a cell to add one appliance of that type to that room. */
export function RoomsGridPage() {
  const navigate = useNavigate();
  const { rooms, inventory, addAppliance, updateQuantity, addCustomRoom } = useInventory();
  const [adding, setAdding] = useState(false);
  const [roomName, setRoomName] = useState('');
  const [roomError, setRoomError] = useState<string | null>(null);

  const countFor = (roomId: string, catalogueId: string) => {
    const item = inventory.find((i) => i.roomId === roomId && i.catalogueId === catalogueId && i.relayChannel == null);
    return { item, count: item?.quantity ?? 0 };
  };

  const addRoom = (e: React.FormEvent) => {
    e.preventDefault();
    if (!roomName.trim()) return;
    if (!addCustomRoom(roomName)) {
      setRoomError('That space already exists.');
      return;
    }
    setRoomName('');
    setRoomError(null);
    setAdding(false);
  };

  return (
    <div className="page">
      <PageHero art="room" title={<>Bring your<br />home to life</>} subtitle="Tell us what’s in each room to understand your energy use." />

      <section className="sheet" aria-label="Appliances by room">
        <div className="grid-matrix" role="grid">
          <div className="grid-matrix__corner">Rooms <ChevronDown size={16} /></div>
          {GRID_COLUMNS.map((col) => (
            <div key={col.label} className="grid-matrix__head" role="columnheader">
              <ApplianceIcon type={col.icon} size={28} />
              <span>{col.label}</span>
            </div>
          ))}

          {rooms.map((room) => (
            <div key={room.id} className="grid-matrix__row" role="row">
              <div className="grid-matrix__room" role="rowheader">
                <RoomIcon name={room.name} size={26} />
                <span>{room.name}</span>
              </div>
              {GRID_COLUMNS.map((col) => {
                const { item, count } = countFor(room.id, col.catalogueId);
                const catalogue = CATALOGUE.get(col.catalogueId);
                return (
                  <div key={col.label} className={`grid-matrix__cell ${count > 0 ? 'is-on' : ''}`} role="gridcell">
                    <button
                      type="button"
                      className="grid-matrix__tap"
                      onClick={() => catalogue && addAppliance(catalogue, room.id, 1)}
                      aria-label={`Add ${col.label} to ${room.name}`}
                    >
                      {count > 0 ? (
                        <>
                          <ApplianceIcon type={col.icon} size={26} />
                          <b>{count}</b>
                        </>
                      ) : (
                        <PlusIcon size={18} />
                      )}
                    </button>
                    {item && (
                      <button
                        type="button"
                        className="grid-matrix__minus"
                        onClick={() => updateQuantity(item.id, -1)}
                        aria-label={`Remove one ${col.label} from ${room.name}`}
                      >
                        −
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </section>

      <section className="card" aria-label="Add custom space">
        <div className="row row--plain">
          <span className="row__icon"><FileIcon size={26} /></span>
          <span className="row__body">
            <span className="row__title">Add custom space</span>
            <span className="row__sub">If your space is not listed above.</span>
          </span>
          <button type="button" className="btn btn--soft btn--small" onClick={() => setAdding((v) => !v)}>
            <PlusIcon size={16} /> Add
          </button>
        </div>
        {adding && (
          <form className="inline-add" onSubmit={addRoom}>
            <input className="form__input" autoFocus value={roomName} onChange={(e) => setRoomName(e.target.value)} placeholder="e.g. Study, Hall, Garage" />
            <button type="submit" className="btn btn--primary btn--small">Save</button>
            {roomError && <p className="form__error">{roomError}</p>}
          </form>
        )}
      </section>

      <button type="button" className="btn btn--primary page__cta" onClick={() => navigate('/devices/summary')}>
        Continue to Summary
        <span className="btn__arrow"><ArrowIcon /></span>
      </button>
    </div>
  );
}
