import { useMemo, useState } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { APPLIANCE_CATEGORIES, type ApplianceIconType, type CatalogueItem } from '../../data/applianceCatalogue';
import { RELAY_CHANNELS } from '../../data/relayChannels';
import { ApplianceIcon } from '../../components/appliances/ApplianceIcons';
import { ApplianceRelayControl } from '../../components/appliances/ApplianceRelayControl';
import { SimControlCard } from '../../components/appliances/SimControlCard';
import { SimTag } from '../../components/appliances/SourceTag';
import { PageHero } from '../../components/art/PageHero';
import { useInventory } from '../../hooks/useInventory';
import type { EssentialStatus } from '../../context/inventoryContextDef';
import { ArrowIcon, ChevronDown, TrashIcon } from '../../components/ui/icons';
import { getDefaultDailyHours } from '../../utils/energyMath';
import './devices.css';

const PICKER: { icon: ApplianceIconType; label: string; category: string; name: string; watts: number }[] = [
  { icon: 'bulb', label: 'Light', category: 'Lighting', name: 'Light', watts: 9 },
  { icon: 'fan', label: 'Fan', category: 'Fans', name: 'Fan', watts: 75 },
  { icon: 'ac', label: 'AC', category: 'Cooling', name: 'AC', watts: 1500 },
  { icon: 'fridge', label: 'Refrigerator', category: 'Refrigerator', name: 'Refrigerator', watts: 150 },
  { icon: 'tv', label: 'TV', category: 'Entertainment', name: 'TV', watts: 100 },
  { icon: 'washer', label: 'Washing Machine', category: 'Washing Machine', name: 'Washing Machine', watts: 500 },
  { icon: 'microwave', label: 'Microwave', category: 'Kitchen', name: 'Microwave', watts: 800 },
  { icon: 'purifier', label: 'Water Purifier', category: 'Water Purifier', name: 'Water Purifier', watts: 60 },
  { icon: 'dishwasher', label: 'Dishwasher', category: 'Kitchen', name: 'Dishwasher', watts: 1200 },
];

const CATEGORY_NAMES = [...APPLIANCE_CATEGORIES.map((c) => c.name), 'Other'];

/** Add (from catalogue or custom) or edit an appliance. */
export function ApplianceFormPage() {
  const { catalogueId, applianceId } = useParams();
  const navigate = useNavigate();
  const { rooms, inventory, addAppliance, updateApplianceDetails, removeAppliance } = useInventory();

  const existing = applianceId ? inventory.find((i) => i.id === applianceId) : undefined;
  const catalogueItem = useMemo(
    () => (catalogueId ? APPLIANCE_CATEGORIES.flatMap((c) => c.items).find((i) => i.id === catalogueId) : undefined),
    [catalogueId]
  );

  if ((applianceId && !existing) || (catalogueId && !catalogueItem)) {
    return <Navigate to="/devices" replace />;
  }

  return (
    <FormBody
      key={existing?.id ?? catalogueItem?.id ?? 'custom'}
      existingId={existing?.id}
      initial={{
        iconType: (existing?.iconType ?? catalogueItem?.iconType ?? 'bulb') as ApplianceIconType,
        name: existing?.name ?? catalogueItem?.name ?? '',
        category: existing?.category ?? catalogueItem?.category ?? 'Other',
        brand: existing?.brand ?? catalogueItem?.brand ?? '',
        model: existing?.model ?? '',
        watts: existing?.ratedWatts ?? catalogueItem?.ratedWatts ?? 0,
        quantity: existing?.quantity ?? 1,
        roomId: existing?.roomId || rooms[0]?.id || '',
        hours:
          existing?.dailyHours ?? getDefaultDailyHours(existing?.category ?? catalogueItem?.category),
        essential: (existing?.isEssential ?? 'unsure') as EssentialStatus,
        relay: existing?.relayChannel ?? null,
        simAuto: existing?.simAuto ?? true,
      }}
      catalogueItem={catalogueItem}
      isCustom={!existing && !catalogueItem}
      navigate={navigate}
      rooms={rooms}
      inventory={inventory}
      addAppliance={addAppliance}
      updateApplianceDetails={updateApplianceDetails}
      removeAppliance={removeAppliance}
    />
  );
}

interface FormState {
  iconType: ApplianceIconType;
  name: string;
  category: string;
  brand: string;
  model: string;
  watts: number;
  quantity: number;
  roomId: string;
  hours: number;
  essential: EssentialStatus;
  /** null = simulated device */
  relay: number | null;
  simAuto: boolean;
}

interface FormBodyProps {
  existingId?: string;
  initial: FormState;
  catalogueItem?: CatalogueItem;
  isCustom: boolean;
  navigate: ReturnType<typeof useNavigate>;
  rooms: ReturnType<typeof useInventory>['rooms'];
  inventory: ReturnType<typeof useInventory>['inventory'];
  addAppliance: ReturnType<typeof useInventory>['addAppliance'];
  updateApplianceDetails: ReturnType<typeof useInventory>['updateApplianceDetails'];
  removeAppliance: ReturnType<typeof useInventory>['removeAppliance'];
}

function FormBody(props: FormBodyProps) {
  const { existingId, catalogueItem, isCustom, navigate, rooms, inventory } = props;
  const [f, setF] = useState<FormState>(props.initial);
  const [error, setError] = useState<string | null>(null);
  const editing = !!existingId;
  const saved = editing ? inventory.find((i) => i.id === existingId) : undefined;

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setF((prev) => ({ ...prev, [key]: value }));
  const freeChannels = RELAY_CHANNELS.filter((ch) => !inventory.some((i) => i.relayChannel === ch && i.id !== existingId));
  const isRelay = f.relay != null;
  const chooseMode = (relay: boolean) => set('relay', relay ? (f.relay ?? freeChannels[0] ?? null) : null);

  const pickIcon = (p: (typeof PICKER)[number]) => {
    setF((prev) => ({
      ...prev,
      iconType: p.icon,
      ...(isCustom ? { category: p.category, name: prev.name && prev.name !== labelFor(prev.iconType) ? prev.name : p.name, watts: prev.watts || p.watts } : {}),
    }));
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!f.name.trim()) return setError('Give the appliance a name.');
    if (!(f.watts > 0)) return setError('Enter the rated power in watts.');
    if (!f.roomId) return setError('Choose a room.');
    if (f.relay != null && !RELAY_CHANNELS.includes(f.relay)) return setError('Choose a relay channel.');
    setError(null);

    if (editing && existingId) {
      props.updateApplianceDetails(existingId, {
        brand: f.brand,
        model: f.model,
        isEssential: f.essential,
        ratedWatts: f.watts,
        quantity: f.quantity,
        roomId: f.roomId,
        dailyHours: f.hours,
        relayChannel: f.relay,
        simAuto: f.simAuto,
      });
      navigate('/devices', { state: { toast: `Saved ${f.name}` } });
      return;
    }

    const item: CatalogueItem = {
      id: catalogueItem?.id ?? `custom-${f.name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-')}`,
      name: f.name.trim(),
      brand: f.brand.trim() || undefined,
      category: f.category,
      ratedWatts: f.watts,
      powerLabel: `${f.watts} W`,
      isExample: false,
      iconType: f.iconType,
    };
    props.addAppliance(item, f.roomId, f.quantity, {
      brand: f.brand,
      model: f.model,
      isEssential: f.essential,
      relayChannel: f.relay,
      dailyHours: f.hours,
      simAuto: f.simAuto,
    });
    const room = rooms.find((r) => r.id === f.roomId)?.name ?? 'your home';
    const how = f.relay != null ? `on relay ${f.relay}` : 'as a simulated device';
    navigate('/devices', { state: { toast: `Added ${f.quantity} × ${item.name} to ${room} ${how}` } });
  };

  const remove = () => {
    if (!existingId) return;
    props.removeAppliance(existingId);
    navigate('/devices', { state: { toast: `Removed ${f.name}` } });
  };

  return (
    <div className="page">
      <PageHero
        art="cottage"
        title={<>Appliance<br />details</>}
        subtitle={editing ? 'Update this appliance.' : 'Add a few details to get more accurate insights and recommendations.'}
      />

      <form className="sheet form" onSubmit={submit} noValidate>
        {!editing && (
          <fieldset className="picker" aria-label="Select appliance">
            <legend className="form__label">Select appliance</legend>
            <div className="picker__grid">
              {PICKER.map((p) => (
                <button
                  key={p.icon + p.label}
                  type="button"
                  className={`picker__item ${f.iconType === p.icon ? 'is-on' : ''}`}
                  onClick={() => pickIcon(p)}
                  aria-pressed={f.iconType === p.icon}
                >
                  <ApplianceIcon type={p.icon} size={30} />
                  <span>{p.label}</span>
                </button>
              ))}
            </div>
          </fieldset>
        )}

        <div className="form__grid">
          <label className="form__field">
            <span className="form__label">Appliance name</span>
            <input className="form__input" value={f.name} onChange={(e) => set('name', e.target.value)} disabled={editing} placeholder="e.g. Ceiling Fan" />
          </label>
          <label className="form__field">
            <span className="form__label">Category</span>
            <span className="form__select-wrap">
              <select className="form__input" value={f.category} onChange={(e) => set('category', e.target.value)} disabled={editing}>
                {CATEGORY_NAMES.map((c) => <option key={c}>{c}</option>)}
              </select>
              <ChevronDown className="form__chev" />
            </span>
          </label>
          <label className="form__field">
            <span className="form__label">Brand <i>(optional)</i></span>
            <input className="form__input" value={f.brand} onChange={(e) => set('brand', e.target.value)} placeholder="e.g. Philips" maxLength={40} />
          </label>
          <label className="form__field">
            <span className="form__label">Model <i>(optional)</i></span>
            <input className="form__input" value={f.model} onChange={(e) => set('model', e.target.value)} placeholder="e.g. 9W LED" maxLength={50} />
          </label>
          <label className="form__field">
            <span className="form__label">Rated power (W)</span>
            <input className="form__input" type="number" inputMode="numeric" min={1} max={10000} value={f.watts || ''} onChange={(e) => set('watts', Math.max(0, Number(e.target.value)))} />
          </label>
          <div className="form__field">
            <span className="form__label">Quantity</span>
            <span className="form__qty">
              <button type="button" className="stepper__btn" onClick={() => set('quantity', Math.max(1, f.quantity - 1))} disabled={f.quantity <= 1} aria-label="Decrease quantity">−</button>
              <span className="stepper__val">{f.quantity}</span>
              <button type="button" className="stepper__btn" onClick={() => set('quantity', Math.min(99, f.quantity + 1))} aria-label="Increase quantity">+</button>
            </span>
          </div>
          <label className="form__field">
            <span className="form__label">Location / room</span>
            <span className="form__select-wrap">
              <select className="form__input" value={f.roomId} onChange={(e) => set('roomId', e.target.value)}>
                {rooms.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
              <ChevronDown className="form__chev" />
            </span>
          </label>
          <div className="form__field">
            <span className="form__label">Essential?</span>
            <span className="seg3" role="radiogroup" aria-label="Essential">
              {(['yes', 'no', 'unsure'] as EssentialStatus[]).map((v) => (
                <button key={v} type="button" role="radio" aria-checked={f.essential === v} className={f.essential === v ? 'is-on' : ''} onClick={() => set('essential', v)}>
                  {v === 'yes' ? 'Yes' : v === 'no' ? 'No' : 'Not sure'}
                </button>
              ))}
            </span>
          </div>
          <label className="form__field">
            <span className="form__label">Hours used per day</span>
            <input className="form__input" type="number" inputMode="decimal" min={0} max={24} step={0.5} value={f.hours} onChange={(e) => set('hours', Math.min(24, Math.max(0, Number(e.target.value))))} />
          </label>
        </div>

        <fieldset className="connection" aria-label="How SHEM controls this appliance">
          <legend className="form__label">Connection</legend>
          <div className="connection__opts" role="radiogroup">
            <button
              type="button"
              role="radio"
              aria-checked={!isRelay}
              className={`connection__opt ${!isRelay ? 'is-on' : ''}`}
              onClick={() => chooseMode(false)}
            >
              <b>Simulated device <SimTag compact /></b>
              <span>Realistic power model with an on/off switch and a daily routine.</span>
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={isRelay}
              className={`connection__opt ${isRelay ? 'is-on' : ''}`}
              onClick={() => chooseMode(true)}
              disabled={!isRelay && freeChannels.length === 0}
            >
              <b>Real relay</b>
              <span>
                {!isRelay && freeChannels.length === 0
                  ? `Relay ${RELAY_CHANNELS[0]} is used by ${inventory.find((i) => i.relayChannel === RELAY_CHANNELS[0])?.name ?? 'another appliance'}.`
                  : 'Physically switched and measured by the SHEM meter.'}
              </span>
            </button>
          </div>

          {isRelay ? (
            <label className="form__field">
              <span className="form__label">Relay channel</span>
              <span className="form__select-wrap">
                <select className="form__input" value={f.relay ?? ''} onChange={(e) => set('relay', Number(e.target.value))}>
                  {RELAY_CHANNELS.map((ch) => {
                    const usedBy = inventory.find((i) => i.relayChannel === ch && i.id !== existingId);
                    return (
                      <option key={ch} value={ch} disabled={!!usedBy}>
                        Relay {ch}{usedBy ? ` — used by ${usedBy.name}` : ''}
                      </option>
                    );
                  })}
                </select>
                <ChevronDown className="form__chev" />
              </span>
            </label>
          ) : (
            <div className="form__field">
              <span className="form__label">Daily routine</span>
              <span className="seg3" role="radiogroup" aria-label="Daily routine">
                <button type="button" role="radio" aria-checked={f.simAuto} className={f.simAuto ? 'is-on' : ''} onClick={() => set('simAuto', true)}>
                  Follow routine
                </button>
                <button type="button" role="radio" aria-checked={!f.simAuto} className={!f.simAuto ? 'is-on' : ''} onClick={() => set('simAuto', false)}>
                  Manual only
                </button>
              </span>
              <span className="connection__hint">
                {f.simAuto
                  ? f.hours > 0
                    ? `Runs about ${f.hours} h a day at typical times for this appliance. Your on/off switch overrides it until the next scheduled change.`
                    : 'Set “Hours used per day” above for the routine to run. Until then use the on/off switch.'
                  : 'Uses power only while you switch it on in the app.'}
              </span>
            </div>
          )}
        </fieldset>

        {saved?.relayChannel != null && saved.relayChannel === f.relay && <ApplianceRelayControl applianceName={saved.name} channel={saved.relayChannel} />}
        {saved && saved.relayChannel == null && f.relay == null && <SimControlCard applianceId={saved.id} applianceName={saved.name} />}

        {error && <p className="form__error" role="alert">{error}</p>}

        <button type="submit" className="btn btn--primary" id="btn-save-appliance">
          {editing ? 'Save changes' : 'Save appliance'}
          <span className="btn__arrow"><ArrowIcon /></span>
        </button>
        {editing ? (
          <button type="button" className="btn-link btn-link--danger" onClick={remove}><TrashIcon /> Remove appliance</button>
        ) : (
          <button type="button" className="btn-link" onClick={() => navigate(-1)}>Skip for now</button>
        )}
      </form>
    </div>
  );
}

function labelFor(icon: string): string {
  return PICKER.find((p) => p.icon === icon)?.name ?? '';
}
