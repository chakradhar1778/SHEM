import { useId, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useHomeConfig } from '../hooks/useHomeConfig';
import { PageHero } from '../components/art/PageHero';
import { ArrowIcon, HomeTypeIcon, OccupantsIcon, PinIcon, ShieldIcon, ChevronDown } from '../components/ui/icons';

const HOME_TYPES = ['Apartment', 'Independent House', 'Villa', 'Studio'];
const CITIES = ['Bengaluru', 'Mumbai', 'Delhi', 'Hyderabad', 'Chennai', 'Pune', 'Kolkata'];

/** First-run "Let's set up your home" (also used to edit the home later). */
export function HomeSetupPage({ isEditMode = false }: { isEditMode?: boolean }) {
  const navigate = useNavigate();
  const { config, saveConfig } = useHomeConfig();

  const [homeName, setHomeName] = useState(config.homeName || 'My Home');
  const [homeType, setHomeType] = useState(config.homeType || 'Apartment');
  const [occupants, setOccupants] = useState(config.occupants || 4);
  const [location, setLocation] = useState(config.location || '');
  const cityListId = useId();

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    saveConfig({
      ...config,
      homeName: homeName.trim() || 'My Home',
      homeType,
      occupants,
      location: location.trim(),
      isConfigured: true,
    });
    navigate(isEditMode ? '/' : '/devices/rooms');
  };

  return (
    <div className="page">
      <PageHero
        art="blocks"
        layout="wide"
        title={isEditMode ? <>Configure<br />your home</> : <>Let’s set up<br />your home</>}
        subtitle={isEditMode ? 'Update your home details any time.' : 'A clearer view of the energy you use.'}
      />

      <form className="sheet" onSubmit={submit}>
        {isEditMode && (
          <label className="field-row">
            <span className="field-row__icon"><HomeTypeIcon /></span>
            <span className="field-row__body">
              <span className="field-row__label">Home name</span>
              <input className="field-row__input" value={homeName} onChange={(e) => setHomeName(e.target.value)} placeholder="e.g. My Home" maxLength={40} />
            </span>
          </label>
        )}
        <label className="field-row">
          <span className="field-row__icon"><HomeTypeIcon /></span>
          <span className="field-row__body">
            <span className="field-row__label">Home type</span>
            <select className="field-row__select" value={homeType} onChange={(e) => setHomeType(e.target.value)}>
              {HOME_TYPES.map((t) => <option key={t}>{t}</option>)}
            </select>
          </span>
          <ChevronDown className="field-row__chev" />
        </label>

        <div className="field-row">
          <span className="field-row__icon"><OccupantsIcon /></span>
          <span className="field-row__body">
            <span className="field-row__label">Number of occupants</span>
          </span>
          <div className="stepper" role="group" aria-label="Number of occupants">
            <button type="button" className="stepper__btn" onClick={() => setOccupants((n) => Math.max(1, n - 1))} disabled={occupants <= 1} aria-label="Fewer occupants">−</button>
            <span className="stepper__val" aria-live="polite">{occupants}</span>
            <button type="button" className="stepper__btn" onClick={() => setOccupants((n) => Math.min(20, n + 1))} disabled={occupants >= 20} aria-label="More occupants">+</button>
          </div>
        </div>

        <label className="field-row">
          <span className="field-row__icon"><PinIcon /></span>
          <span className="field-row__body">
            <span className="field-row__label">Location (optional)</span>
            <input
              className="field-row__input"
              list={cityListId}
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="e.g. Bengaluru"
            />
            <datalist id={cityListId}>{CITIES.map((c) => <option key={c} value={c} />)}</datalist>
          </span>
          <ChevronDown className="field-row__chev" />
        </label>

        <button type="submit" className="btn btn--primary" id="btn-create-home">
          {isEditMode ? 'Save changes' : 'Create Home'}
          <span className="btn__arrow"><ArrowIcon /></span>
        </button>

        <div className="privacy">
          <span className="privacy__badge"><ShieldIcon /></span>
          <span><strong>Your data stays private.</strong>Only you can see your appliances and bills.</span>
        </div>
      </form>
    </div>
  );
}
