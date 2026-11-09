import { Link } from 'react-router-dom';
import { APPLIANCE_CATEGORIES } from '../../data/applianceCatalogue';
import { ApplianceIcon } from '../../components/appliances/ApplianceIcons';
import { PageHero } from '../../components/art/PageHero';
import { ChevronRight, HelpIcon, PlusIcon } from '../../components/ui/icons';
import './devices.css';

/** Add device: pick a category (or a custom device) to start adding an appliance. */
export function AddDevicePage() {
  return (
    <div className="page">
      <PageHero art="villa" title={<>Add<br />device</>} subtitle="Select a device to add to your home and track its energy usage." />

      <section className="sheet" aria-label="Add appliance">
        <div className="card__head">
          <div>
            <h2 className="card__title">Choose a category</h2>
            <p className="sheet__hint">Pick the type of device you want to add.</p>
          </div>
          <Link to="/devices/rooms" className="link-more"><HelpIcon size={16} /> Quick add</Link>
        </div>

        <div className="cat-grid">
          {APPLIANCE_CATEGORIES.map((cat) => (
            <Link key={cat.id} to={`/devices/category/${cat.id}`} className="cat-card">
              <span className="cat-card__tile"><ApplianceIcon type={cat.iconType} size={34} /></span>
              <span className="cat-card__body">
                <span className="cat-card__name">{cat.name}</span>
                <span className="cat-card__sub">{cat.subtitle}</span>
              </span>
              <ChevronRight className="cat-card__chev" />
            </Link>
          ))}
        </div>

        <Link to="/devices/custom" className="row row--cta">
          <span className="plus-dot"><PlusIcon size={20} /></span>
          <span className="row__body">
            <span className="row__title">Add custom device</span>
            <span className="row__sub">Can’t find your device? Add it manually.</span>
          </span>
          <span className="row__end"><ChevronRight /></span>
        </Link>
      </section>
    </div>
  );
}
