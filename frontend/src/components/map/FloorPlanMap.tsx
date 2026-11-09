import type { Room, InventoryItem } from '../../context/inventoryContextDef';
import { ApplianceIcon } from '../appliances/ApplianceIcons';
import { formatRatedPower } from '../../utils/energyMath';
import './FloorPlanMap.css';

interface FloorPlanMapProps {
  rooms: Room[];
  inventory: InventoryItem[];
  selectedItemId: string | null;
  onSelectItem: (itemId: string | null) => void;
  onOpenDetails: (item: InventoryItem) => void;
  onNavigateToDevices: () => void;
}

// Room architectural illustration accents
function RoomAccentIllustration({ roomId }: { roomId: string }) {
  if (roomId.includes('bed')) {
    return (
      <svg className="room-ambient-svg" viewBox="0 0 140 100" fill="none" aria-hidden="true">
        {/* Bed outline */}
        <rect x="25" y="30" width="60" height="55" rx="5" fill="#E2E8F0" opacity="0.45" />
        <rect x="30" y="33" width="22" height="15" rx="3" fill="#CBD5E1" opacity="0.6" />
        <rect x="58" y="33" width="22" height="15" rx="3" fill="#CBD5E1" opacity="0.6" />
        <path d="M25 55 H85 V85 H25 Z" fill="#F1F5F9" opacity="0.7" />
        {/* Nightstand */}
        <rect x="10" y="35" width="12" height="16" rx="2" fill="#E2E8F0" opacity="0.5" />
        {/* Plant */}
        <circle cx="105" cy="40" r="8" fill="#D1FAE5" opacity="0.6" />
        <circle cx="105" cy="40" r="4" fill="#10B981" opacity="0.3" />
      </svg>
    );
  }
  if (roomId.includes('living')) {
    return (
      <svg className="room-ambient-svg" viewBox="0 0 140 100" fill="none" aria-hidden="true">
        {/* Sofa */}
        <rect x="20" y="25" width="70" height="26" rx="6" fill="#E2E8F0" opacity="0.5" />
        <rect x="23" y="28" width="64" height="12" rx="3" fill="#CBD5E1" opacity="0.5" />
        {/* Coffee table */}
        <rect x="35" y="58" width="40" height="20" rx="4" fill="#F1F5F9" stroke="#E2E8F0" strokeWidth="1.5" />
        {/* Armchair */}
        <rect x="100" y="35" width="24" height="24" rx="4" fill="#E2E8F0" opacity="0.4" />
        {/* Rug */}
        <rect x="25" y="52" width="60" height="32" rx="4" fill="#F8FAFC" stroke="#E2E8F0" strokeWidth="1" strokeDasharray="3 3" opacity="0.7" />
      </svg>
    );
  }
  if (roomId.includes('kitchen')) {
    return (
      <svg className="room-ambient-svg" viewBox="0 0 140 100" fill="none" aria-hidden="true">
        {/* Kitchen counter L-shape */}
        <path d="M15 15 H55 V35 H35 V85 H15 Z" fill="#E2E8F0" opacity="0.45" />
        {/* Stove circles */}
        <circle cx="25" cy="45" r="4" fill="#CBD5E1" opacity="0.7" />
        <circle cx="25" cy="62" r="4" fill="#CBD5E1" opacity="0.7" />
        {/* Dining table */}
        <rect x="68" y="35" width="48" height="32" rx="6" fill="#F8FAFC" stroke="#E2E8F0" strokeWidth="1.5" />
        {/* Chairs */}
        <rect x="74" y="26" width="14" height="6" rx="2" fill="#CBD5E1" opacity="0.5" />
        <rect x="94" y="26" width="14" height="6" rx="2" fill="#CBD5E1" opacity="0.5" />
        <rect x="74" y="70" width="14" height="6" rx="2" fill="#CBD5E1" opacity="0.5" />
        <rect x="94" y="70" width="14" height="6" rx="2" fill="#CBD5E1" opacity="0.5" />
      </svg>
    );
  }
  if (roomId.includes('bath')) {
    return (
      <svg className="room-ambient-svg" viewBox="0 0 140 100" fill="none" aria-hidden="true">
        {/* Shower enclosure */}
        <rect x="15" y="15" width="36" height="36" rx="4" fill="#E0F2FE" opacity="0.5" stroke="#BAE6FD" strokeWidth="1" />
        <circle cx="33" cy="33" r="5" fill="#38BDF8" opacity="0.4" />
        {/* Vanity / sink */}
        <rect x="75" y="20" width="34" height="22" rx="4" fill="#F1F5F9" stroke="#E2E8F0" strokeWidth="1.5" />
        <ellipse cx="92" cy="31" rx="8" ry="6" fill="#E2E8F0" opacity="0.6" />
        {/* Commode */}
        <rect x="80" y="60" width="22" height="26" rx="10" fill="#E2E8F0" opacity="0.5" />
      </svg>
    );
  }
  if (roomId.includes('balcony')) {
    return (
      <svg className="room-ambient-svg" viewBox="0 0 140 100" fill="none" aria-hidden="true">
        {/* Balcony railing */}
        <line x1="15" y1="85" x2="125" y2="85" stroke="#CBD5E1" strokeWidth="2" strokeDasharray="6 4" />
        {/* Potted plants */}
        <circle cx="30" cy="50" r="10" fill="#D1FAE5" opacity="0.6" />
        <circle cx="30" cy="50" r="5" fill="#10B981" opacity="0.3" />
        <circle cx="105" cy="50" r="10" fill="#D1FAE5" opacity="0.6" />
        <circle cx="105" cy="50" r="5" fill="#10B981" opacity="0.3" />
      </svg>
    );
  }

  // Generic custom room accent
  return (
    <svg className="room-ambient-svg" viewBox="0 0 140 100" fill="none" aria-hidden="true">
      <rect x="25" y="25" width="90" height="50" rx="6" fill="#F8FAFC" stroke="#E2E8F0" strokeWidth="1" strokeDasharray="4 4" opacity="0.6" />
      <circle cx="70" cy="50" r="12" fill="#E2E8F0" opacity="0.3" />
    </svg>
  );
}

export function FloorPlanMap({
  rooms,
  inventory,
  selectedItemId,
  onSelectItem,
  onOpenDetails,
  onNavigateToDevices,
}: FloorPlanMapProps) {
  // Find selected item
  const selectedItem = selectedItemId
    ? inventory.find((i) => i.id === selectedItemId) || null
    : null;

  return (
    <div className="floorplan-container">
      {/* 3D Isometric / Architectural Shell */}
      <div className="floorplan-shell">
        <div className="floorplan-grid">
          {rooms.map((room) => {
            const roomAppliances = inventory.filter((item) => item.roomId === room.id);

            return (
              <div
                key={room.id}
                className={`floorplan-room floorplan-room--${room.id.replace('room-', '')}`}
                data-room-id={room.id}
              >
                {/* Room Label Badge */}
                <div className="floorplan-room__header">
                  <span className="floorplan-room__icon">{room.icon || '🏠'}</span>
                  <span className="floorplan-room__name">{room.name}</span>
                  {roomAppliances.length > 0 && (
                    <span className="floorplan-room__count" title={`${roomAppliances.length} configured appliances`}>
                      {roomAppliances.length}
                    </span>
                  )}
                </div>

                {/* Ambient Floor Visuals */}
                <div className="floorplan-room__canvas">
                  <RoomAccentIllustration roomId={room.id} />

                  {/* Appliance Markers in Room */}
                  <div className="floorplan-room__markers">
                    {roomAppliances.length === 0 ? (
                      <div className="floorplan-room__empty">
                        <span className="floorplan-room__empty-text">No devices</span>
                      </div>
                    ) : (
                      roomAppliances.map((item) => {
                        const isSelected = selectedItem?.id === item.id;
                        const isRunning = (item.dailyHours ?? 0) > 0;

                        return (
                          <div
                            key={item.id}
                            className={`appliance-pin-wrapper ${isSelected ? 'is-selected' : ''}`}
                          >
                            {/* Selected Callout Card matching New Screen7.png */}
                            {isSelected && (
                              <div
                                className="appliance-callout"
                                role="dialog"
                                aria-label={`Details for ${item.name}`}
                              >
                                <div className="appliance-callout__inner">
                                  <div className="appliance-callout__icon-box">
                                    <ApplianceIcon type={item.iconType} size={24} />
                                  </div>
                                  <div className="appliance-callout__info">
                                    <div className="appliance-callout__title-row">
                                      <h4 className="appliance-callout__name">{item.name}</h4>
                                      {item.quantity > 1 && (
                                        <span className="appliance-callout__qty">×{item.quantity}</span>
                                      )}
                                    </div>
                                    <div className="appliance-callout__power">
                                      {formatRatedPower(item.ratedWatts)}
                                      <span className="appliance-callout__power-label"> rated</span>
                                    </div>
                                    <div className="appliance-callout__status">
                                      <span
                                        className={`appliance-callout__status-dot ${isRunning ? 'is-running' : 'is-off'}`}
                                      />
                                      <span className="appliance-callout__status-text">
                                        {item.dailyHours ?? 0} h/day (configured)
                                      </span>
                                    </div>
                                  </div>
                                  <button
                                    type="button"
                                    className="appliance-callout__chevron-btn"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      onOpenDetails(item);
                                    }}
                                    title="View full device details"
                                    aria-label="View device details"
                                  >
                                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                      <path d="M9 18l6-6-6-6" />
                                    </svg>
                                  </button>
                                </div>
                                <div className="appliance-callout__beak" />
                              </div>
                            )}

                            {/* Pin Circular Button */}
                            <button
                              type="button"
                              className={`appliance-pin ${isRunning ? 'is-running' : 'is-off'} ${isSelected ? 'is-active' : ''}`}
                              onClick={() => {
                                if (isSelected) {
                                  onSelectItem(null);
                                } else {
                                  onSelectItem(item.id);
                                }
                              }}
                              title={`${item.name} (${formatRatedPower(item.ratedWatts)} rated, ${item.dailyHours ?? 0} h/day configured)`}
                              aria-label={`Select ${item.name}`}
                            >
                              <span className="appliance-pin__icon">
                                <ApplianceIcon type={item.iconType} size={22} />
                              </span>

                              {/* Multi-quantity pill if > 1 */}
                              {item.quantity > 1 && (
                                <span className="appliance-pin__qty-badge">×{item.quantity}</span>
                              )}

                              {/* Status dot on bottom-right */}
                              <span
                                className={`appliance-pin__dot ${isRunning ? 'is-running' : 'is-off'}`}
                                aria-hidden="true"
                              />
                            </button>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer prompt to edit rooms in Devices */}
      <div className="floorplan-edit-bar">
        <span className="floorplan-edit-bar__hint">
          Need to reassign appliances or add custom rooms?
        </span>
        <button
          type="button"
          className="floorplan-edit-bar__btn"
          onClick={onNavigateToDevices}
        >
          Edit in Devices →
        </button>
      </div>
    </div>
  );
}
