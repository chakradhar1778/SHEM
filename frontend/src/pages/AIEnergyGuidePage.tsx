import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchRecommendations } from '../api/insightsApi';
import type { EnergyRecommendation } from '../api/types';
import { useApiQuery } from '../hooks/useApiQuery';
import { PageHero } from '../components/art/PageHero';
import { ArrowIcon, BoltIcon, ChevronDown, InfoIcon } from '../components/ui/icons';
import './AIEnergyGuidePage.css';

const PRIORITY: Record<EnergyRecommendation['priority'], { label: string; tone: string }> = {
  high: { label: 'High impact', tone: 'tone--amber' },
  medium: { label: 'Worth a look', tone: 'tone--blue' },
  low: { label: 'Tip', tone: 'tone--green' },
};

/** Rule-based tips drawn from the meter readings and the appliance list. */
export function AIEnergyGuidePage() {
  const navigate = useNavigate();
  const { data: tips, error, refresh } = useApiQuery(fetchRecommendations, 'recommendations', 300_000);
  const [noted, setNoted] = useState<Record<string, boolean>>({});
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const flip = (setter: typeof setNoted, id: string) => setter((p) => ({ ...p, [id]: !p[id] }));

  const [featured, ...rest] = tips ?? [];

  return (
    <div className="page">
      <PageHero art="cottage" title={<>Your energy<br />guide</>} subtitle="Small changes. Smarter energy.">
        <span className="status-pill is-live"><BoltIcon size={14} /> Based on your data</span>
      </PageHero>

      {!tips ? (
        <section className="card" role={error ? 'alert' : 'status'}>
          <h2 className="card__title">{error ? 'Could not load guidance' : 'Loading guidance…'}</h2>
          {error && (<><p className="sheet__hint">{error}</p><button type="button" className="btn btn--soft btn--small" onClick={refresh}>Try again</button></>)}
        </section>
      ) : !featured ? (
        <section className="card">
          <div className="empty">
            <BoltIcon size={26} />
            <span>
              <strong>Nothing to flag right now.</strong>
              Tips appear when your readings or appliances show a clear pattern, like a high overnight load or a month heading over budget.
            </span>
          </div>
          <button type="button" className="btn btn--soft" style={{ marginTop: 12 }} onClick={() => navigate('/devices')}>Review appliances</button>
        </section>
      ) : (
        <>
          <section className={`card tip tip--featured ${PRIORITY[featured.priority].tone}`}>
            <span className="tip__badge">{PRIORITY[featured.priority].label}</span>
            <h2 className="tip__title">{featured.title}</h2>
            <p className="tip__desc">{featured.description}</p>
            <div className="btn-row">
              <button type="button" className={`btn btn--small ${noted[featured.id] ? 'btn--soft' : 'btn--primary'}`} onClick={() => flip(setNoted, featured.id)}>
                {noted[featured.id] ? '✓ Noted' : 'I’ll try this'}
              </button>
              <button type="button" className="btn btn--soft btn--small" onClick={() => flip(setOpen, featured.id)} aria-expanded={!!open[featured.id]}>
                {open[featured.id] ? 'Hide' : 'Why this tip?'}
              </button>
            </div>
            {open[featured.id] && <p className="tip__why"><b>Based on:</b> {featured.evidence}</p>}
          </section>

          {rest.map((t) => (
            <section key={t.id} className={`card tip ${PRIORITY[t.priority].tone}`}>
              <div className="tip__row">
                <div>
                  <span className="tip__badge">{PRIORITY[t.priority].label}</span>
                  <h3 className="tip__title tip__title--sm">{t.title}</h3>
                </div>
                <button type="button" className={`chip ${noted[t.id] ? 'chip--navy chip--on' : ''}`} onClick={() => flip(setNoted, t.id)}>
                  {noted[t.id] ? '✓ Noted' : 'Noted'}
                </button>
              </div>
              <p className="tip__desc">{t.description}</p>
              <button type="button" className="link-more" onClick={() => flip(setOpen, t.id)}>
                <InfoIcon /> Why am I seeing this? <ChevronDown size={14} />
              </button>
              {open[t.id] && <p className="tip__why">{t.evidence}</p>}
            </section>
          ))}

          <button type="button" className="btn btn--primary" onClick={() => navigate('/insights/daily')}>
            View Energy today <span className="btn__arrow"><ArrowIcon /></span>
          </button>
        </>
      )}

      <p className="source-note">Tips come from simple rules on your measured readings and appliance list. Costs are estimates at your tariff, not utility bills.</p>
    </div>
  );
}
