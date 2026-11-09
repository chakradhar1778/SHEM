import React, { useState } from 'react';
import type { InventoryItem, Room, EssentialStatus } from '../../context/inventoryContextDef';
import { useInventory } from '../../hooks/useInventory';
import { ApplianceIcon } from './ApplianceIcons';
import '../../pages/DevicesPage.css'; // legacy modal styles, retired with the map page redesign
import { RELAY_CHANNELS } from '../../data/relayChannels';
import {
  calculateConfiguredRatedWatts,
  calculateDailyKWh,
  calculateMonthlyKWh,
  formatKWh,
} from '../../utils/energyMath';

interface ApplianceDetailModalProps {
  item: InventoryItem;
  room?: Room;
  rooms?: Room[];
  onClose: () => void;
  onUpdateDailyHours?: (itemId: string, hours: number) => void;
  onSave?: (
    itemId: string,
    updates: {
      brand?: string;
      model?: string;
      isEssential?: EssentialStatus;
      ratedWatts?: number;
      quantity?: number;
      roomId?: string;
      dailyHours?: number;
      relayChannel?: number | null;
    }
  ) => void;
}

export function ApplianceDetailModal({
  item,
  room,
  rooms = [],
  onClose,
  onUpdateDailyHours,
  onSave,
}: ApplianceDetailModalProps) {
  const { updateApplianceDetails, inventory } = useInventory();

  // Form states initialized safely from existing item
  const [brand, setBrand] = useState(item.brand || '');
  const [model, setModel] = useState(item.model || '');
  const [isEssential, setIsEssential] = useState<EssentialStatus>(item.isEssential || 'unsure');
  const [ratedWatts, setRatedWatts] = useState<number>(item.ratedWatts || 0);
  const [quantity, setQuantity] = useState<number>(item.quantity || 1);
  const [selectedRoomId, setSelectedRoomId] = useState<string>(item.roomId || (rooms[0]?.id ?? ''));
  const [dailyHours, setDailyHours] = useState<number>(
    typeof item.dailyHours === 'number' ? item.dailyHours : 4
  );
  const [relayChannel, setRelayChannel] = useState<number | null>(item.relayChannel ?? null);
  const [isSavedFeedback, setIsSavedFeedback] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  // Dynamic live calculations based on user input
  const validWatts = Math.max(1, ratedWatts || 1);
  const validQty = Math.max(1, quantity || 1);
  const totalRatedWatts = calculateConfiguredRatedWatts(validWatts, validQty);
  const dailyKWh = calculateDailyKWh(validWatts, validQty, dailyHours);
  const monthlyKWh = calculateMonthlyKWh(dailyKWh);

  const handleHourStep = (delta: number) => {
    setDailyHours((prev) => Math.max(0, Math.min(24, Math.round((prev + delta) * 2) / 2)));
  };

  const handleHourInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    if (!isNaN(val)) {
      setDailyHours(Math.max(0, Math.min(24, Math.round(val * 2) / 2)));
    }
  };

  const handleQuantityStep = (delta: number) => {
    setQuantity((prev) => Math.max(1, Math.min(99, prev + delta)));
  };

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();

    if (ratedWatts <= 0 || isNaN(ratedWatts)) {
      setValidationError('Please enter a valid rated wattage greater than 0.');
      return;
    }
    if (quantity <= 0 || isNaN(quantity)) {
      setValidationError('Please enter a valid quantity of 1 or more.');
      return;
    }

    setValidationError(null);
    setIsSavedFeedback(true);

    const updates = {
      brand: brand.trim() || undefined,
      model: model.trim() || undefined,
      isEssential,
      ratedWatts: validWatts,
      quantity: validQty,
      roomId: selectedRoomId,
      dailyHours,
      relayChannel,
    };

    if (onSave) {
      onSave(item.id, updates);
    } else {
      updateApplianceDetails(item.id, updates);
      if (onUpdateDailyHours) {
        onUpdateDailyHours(item.id, dailyHours);
      }
    }

    // Brief timeout for smooth visual feedback before closing
    setTimeout(() => {
      onClose();
    }, 250);
  };

  return (
    <div
      className="detail-modal-backdrop"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="detail-modal-title"
    >
      <div
        className="detail-modal"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top Bar with Navigation and Cottage Artwork (Group 14.png) */}
        <div className="detail-modal__header-banner">
          <div className="detail-modal__header-text">
            <button
              type="button"
              className="detail-modal__back-btn"
              onClick={onClose}
              aria-label="Back"
              title="Close modal"
              id="btn-close-appliance-detail"
            >
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M15 18l-6-6 6-6" />
              </svg>
            </button>
            <div>
              <h2 id="detail-modal-title" className="detail-modal__title font-serif">
                Appliance details
              </h2>
              <p className="detail-modal__subtitle">
                Add a few details to get more accurate insights and recommendations.
              </p>
            </div>
          </div>

          {/* Cottage & Sun Decorative Vector Linework */}
          <div className="detail-modal__cottage-art" aria-hidden="true">
            <svg viewBox="0 0 130 90" width="115" height="80" fill="none">
              {/* Warm Sun */}
              <circle cx="88" cy="24" r="18" fill="#FDE047" opacity="0.6" />
              {/* Foliage Blobs */}
              <path d="M72 46 C72 32 90 30 98 40 C106 34 122 42 120 56 C124 64 116 75 106 74 C96 76 86 72 82 66 C74 64 72 54 72 46 Z" fill="#93C5FD" opacity="0.35" />
              <path d="M16 64 C14 52 28 46 36 54 C44 48 56 54 54 66 C58 72 52 80 44 80 C36 82 26 80 22 74 C16 72 16 66 16 64 Z" fill="#60A5FA" opacity="0.3" />
              {/* House Gable Roof */}
              <path d="M38 52 L62 34 L86 52 Z" fill="#1E3A8A" />
              {/* Chimney */}
              <rect x="74" y="36" width="6" height="12" fill="#1E293B" rx="1" />
              {/* House Body */}
              <rect x="42" y="52" width="40" height="28" fill="#FEF3C7" stroke="#CBD5E1" strokeWidth="0.8" rx="2" />
              {/* Door */}
              <rect x="58" y="62" width="9" height="18" fill="#1E3A8A" rx="1" />
              <circle cx="65" cy="71" r="0.8" fill="#FDE047" />
              {/* Windows */}
              <rect x="46" y="58" width="8" height="8" fill="#FEF08A" stroke="#F59E0B" strokeWidth="0.8" rx="1" />
              <rect x="70" y="58" width="8" height="8" fill="#FEF08A" stroke="#F59E0B" strokeWidth="0.8" rx="1" />
            </svg>
          </div>
        </div>

        {/* Selected Appliance Preview Tile */}
        <div className="detail-modal__appliance-tile">
          <div className="detail-modal__tile-icon" aria-hidden="true">
            <ApplianceIcon type={item.iconType} size={30} />
          </div>
          <div className="detail-modal__tile-info">
            <span className="detail-modal__tile-label">Appliance</span>
            <span className="detail-modal__tile-name">{item.name}</span>
            <span className="detail-modal__tile-cat">{item.category}</span>
          </div>
          <div className="detail-modal__tile-badge">
            <span className="room-icon-tag">{room?.icon || '🏠'} {room?.name || 'Assigned'}</span>
          </div>
        </div>

        {/* Validation Error Alert */}
        {validationError && (
          <div className="detail-modal__alert" role="alert">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>{validationError}</span>
          </div>
        )}

        {/* Main Metadata Form Grid (Matching Group 14.png) */}
        <form onSubmit={handleSave} className="detail-modal__form">
          <div className="detail-modal__field-grid">
            {/* Row 1: Appliance name (read-only/reference) & Category */}
            <div className="detail-modal__field">
              <label htmlFor="field-appliance-name" className="detail-modal__label">
                Appliance name
              </label>
              <input
                id="field-appliance-name"
                type="text"
                value={item.name}
                readOnly
                disabled
                className="detail-modal__input detail-modal__input--disabled"
              />
            </div>

            <div className="detail-modal__field">
              <label htmlFor="field-appliance-category" className="detail-modal__label">
                Category
              </label>
              <input
                id="field-appliance-category"
                type="text"
                value={item.category}
                readOnly
                disabled
                className="detail-modal__input detail-modal__input--disabled"
              />
            </div>

            {/* Row 2: Brand (optional) & Model (optional) */}
            <div className="detail-modal__field">
              <label htmlFor="field-brand" className="detail-modal__label">
                Brand <span className="label-opt">(optional)</span>
              </label>
              <input
                id="field-brand"
                type="text"
                value={brand}
                onChange={(e) => setBrand(e.target.value)}
                placeholder="e.g. Philips"
                className="detail-modal__input"
                maxLength={40}
              />
            </div>

            <div className="detail-modal__field">
              <label htmlFor="field-model" className="detail-modal__label">
                Model <span className="label-opt">(optional)</span>
              </label>
              <input
                id="field-model"
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="e.g. 9W LED"
                className="detail-modal__input"
                maxLength={50}
              />
            </div>

            {/* Row 3: Rated power (W) & Quantity */}
            <div className="detail-modal__field">
              <label htmlFor="field-watts" className="detail-modal__label">
                Rated power (W)
              </label>
              <input
                id="field-watts"
                type="number"
                min="1"
                max="10000"
                step="1"
                value={ratedWatts}
                onChange={(e) => setRatedWatts(Math.max(1, parseInt(e.target.value, 10) || 0))}
                className="detail-modal__input"
                required
              />
            </div>

            <div className="detail-modal__field">
              <label htmlFor="field-qty" className="detail-modal__label">
                Quantity
              </label>
              <div className="detail-modal__qty-stepper" role="group" aria-label="Quantity selector">
                <button
                  type="button"
                  className="qty-btn"
                  onClick={() => handleQuantityStep(-1)}
                  disabled={quantity <= 1}
                  aria-label="Decrease quantity"
                >
                  −
                </button>
                <input
                  id="field-qty"
                  type="number"
                  min="1"
                  max="99"
                  value={quantity}
                  onChange={(e) => setQuantity(Math.max(1, Math.min(99, parseInt(e.target.value, 10) || 1)))}
                  className="qty-input"
                />
                <button
                  type="button"
                  className="qty-btn"
                  onClick={() => handleQuantityStep(1)}
                  disabled={quantity >= 99}
                  aria-label="Increase quantity"
                >
                  +
                </button>
              </div>
            </div>

            {/* Row 4: Location / room & Essential? */}
            <div className="detail-modal__field">
              <label htmlFor="field-room" className="detail-modal__label">
                Location / room
              </label>
              <div className="detail-modal__select-wrap">
                <select
                  id="field-room"
                  value={selectedRoomId}
                  onChange={(e) => setSelectedRoomId(e.target.value)}
                  className="detail-modal__select"
                >
                  {rooms.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.icon ? `${r.icon} ` : ''}{r.name}
                    </option>
                  ))}
                </select>
                <span className="select-arrow" aria-hidden="true">▾</span>
              </div>
            </div>

            <div className="detail-modal__field">
              <label htmlFor="field-relay" className="detail-modal__label">
                Relay channel <span className="label-opt">(optional)</span>
              </label>
              <div className="detail-modal__select-wrap">
                <select
                  id="field-relay"
                  value={relayChannel ?? ''}
                  onChange={(e) => setRelayChannel(e.target.value === '' ? null : Number(e.target.value))}
                  className="detail-modal__select"
                >
                  <option value="">Not relay-controlled</option>
                  {RELAY_CHANNELS.map((ch) => {
                    const usedBy = inventory.find((i) => i.relayChannel === ch && i.id !== item.id);
                    return (
                      <option key={ch} value={ch} disabled={!!usedBy}>
                        ⚡ Channel {ch}{usedBy ? ` (used by ${usedBy.name})` : ''}
                      </option>
                    );
                  })}
                </select>
                <span className="select-arrow" aria-hidden="true">▾</span>
              </div>
            </div>

            <div className="detail-modal__field">
              <span className="detail-modal__label">Essential?</span>
              <div className="detail-modal__pill-group" role="radiogroup" aria-label="Essential status">
                <button
                  type="button"
                  role="radio"
                  aria-checked={isEssential === 'yes'}
                  className={`essential-pill ${isEssential === 'yes' ? 'active' : ''}`}
                  onClick={() => setIsEssential('yes')}
                  id="pill-essential-yes"
                >
                  Yes
                </button>
                <button
                  type="button"
                  role="radio"
                  aria-checked={isEssential === 'no'}
                  className={`essential-pill ${isEssential === 'no' ? 'active' : ''}`}
                  onClick={() => setIsEssential('no')}
                  id="pill-essential-no"
                >
                  No
                </button>
                <button
                  type="button"
                  role="radio"
                  aria-checked={isEssential === 'unsure'}
                  className={`essential-pill ${isEssential === 'unsure' ? 'active' : ''}`}
                  onClick={() => setIsEssential('unsure')}
                  id="pill-essential-unsure"
                >
                  Not sure
                </button>
              </div>
            </div>
          </div>

          {/* Operating Hours & Calculated Energy Consumption */}
          <div className="detail-modal__runtime-section">
            <div className="detail-modal__hours-card">
              <div className="detail-modal__hours-info">
                <span className="detail-modal__section-label">Estimated Operating Hours</span>
                <span className="detail-modal__hours-subtitle">
                  Adjust estimated daily runtime to calculate monthly consumption
                </span>
              </div>

              <div className="detail-modal__stepper" role="group" aria-label="Operating hours stepper">
                <button
                  type="button"
                  className="detail-modal__stepper-btn"
                  onClick={() => handleHourStep(-0.5)}
                  disabled={dailyHours <= 0}
                  aria-label="Decrease hours by 0.5"
                  id="btn-hours-minus"
                >
                  −
                </button>
                <div className="detail-modal__hours-display">
                  <input
                    type="number"
                    min="0"
                    max="24"
                    step="0.5"
                    value={dailyHours}
                    onChange={handleHourInputChange}
                    className="detail-modal__hours-input"
                    aria-label="Daily operating hours"
                    id="input-daily-hours"
                  />
                  <span className="detail-modal__hours-unit">hrs/day</span>
                </div>
                <button
                  type="button"
                  className="detail-modal__stepper-btn"
                  onClick={() => handleHourStep(0.5)}
                  disabled={dailyHours >= 24}
                  aria-label="Increase hours by 0.5"
                  id="btn-hours-plus"
                >
                  +
                </button>
              </div>
            </div>

            {/* Calculated Energy Estimates Card */}
            <div className="detail-modal__energy-card">
              <div className="detail-modal__energy-header">
                <span className="detail-modal__section-label">Energy Consumption Estimates</span>
                <span className="detail-modal__energy-formula">
                  {validWatts} W × {validQty} units = {totalRatedWatts} W
                </span>
              </div>

              <div className="detail-modal__energy-stats">
                <div className="detail-modal__energy-stat-box">
                  <span className="energy-stat-value" id="val-daily-kwh">
                    {formatKWh(dailyKWh)} <span className="energy-stat-unit">kWh/day</span>
                  </span>
                  <span className="energy-stat-label">Daily Estimate</span>
                  <span className="energy-stat-sublabel">({totalRatedWatts} W × {dailyHours} h / 1000)</span>
                </div>

                <div className="detail-modal__energy-stat-box detail-modal__energy-stat-box--monthly">
                  <span className="energy-stat-value" id="val-monthly-kwh">
                    {formatKWh(monthlyKWh, 2)} <span className="energy-stat-unit">kWh/month</span>
                  </span>
                  <span className="energy-stat-label">Monthly Estimate</span>
                  <span className="energy-stat-sublabel">({formatKWh(dailyKWh)} × 30 days)</span>
                </div>
              </div>

            </div>
          </div>

          {/* "Why this helps" Callout Card (Group 14.png) */}
          <div className="detail-modal__why-helps-card">
            <div className="why-helps__icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#2563EB" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 18h6 M10 22h4 M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.76.76 1.23 1.52 1.41 2.5" />
              </svg>
            </div>
            <div className="why-helps__text">
              <h4 className="why-helps__title">Why this helps</h4>
              <p className="why-helps__desc">Helps estimate load and tailor saving tips.</p>
            </div>
          </div>

          {/* Action Buttons (Group 14.png) */}
          <div className="detail-modal__actions">
            <button
              type="submit"
              className={`detail-modal__save-btn ${isSavedFeedback ? 'saved' : ''}`}
              id="btn-save-appliance-details"
            >
              <span>{isSavedFeedback ? 'Saved ✓' : 'Save appliance'}</span>
              {!isSavedFeedback && (
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 12h14m-7-7l7 7-7 7" />
                </svg>
              )}
            </button>

            <button
              type="button"
              className="detail-modal__cancel-btn"
              onClick={onClose}
              id="btn-cancel-appliance-detail"
            >
              Skip for now
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
