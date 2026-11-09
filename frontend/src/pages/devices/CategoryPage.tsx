import { Link, Navigate, useParams } from 'react-router-dom';
import { APPLIANCE_CATEGORIES } from '../../data/applianceCatalogue';
import { ApplianceIcon } from '../../components/appliances/ApplianceIcons';
import { PageHero } from '../../components/art/PageHero';
import { ChevronRight, PlusIcon } from '../../components/ui/icons';
import './devices.css';

/** One category: pick a model to add. */
export function CategoryPage() {
  const { categoryId } = useParams();
  const category = APPLIANCE_CATEGORIES.find((c) => c.id === categoryId);
  if (!category) return <Navigate to="/devices" replace />;

  return (
    <div className="page">
      <PageHero
        art="villa"
        eyebrow="Add appliance"
        title={category.name}
        subtitle={category.description}
        aside={<span className="hero-tile"><ApplianceIcon type={category.iconType} size={64} /></span>}
      />

      <section className="stack" aria-label={`${category.name} models`}>
        {category.items.map((item) => (
          <Link key={item.id} to={`/devices/new/${item.id}`} className="model-card">
            <span className="model-card__tile"><ApplianceIcon type={item.iconType} size={42} /></span>
            <span className="model-card__body">
              <span className="model-card__name">{item.name}</span>
              <span className="model-card__sub">{[item.brand, `${item.ratedWatts} W`].filter(Boolean).join(' · ')}</span>
            </span>
            <span className="model-card__add" aria-label={`Add ${item.name}`}><PlusIcon size={20} /></span>
          </Link>
        ))}

        <Link to="/devices/custom" className="row row--cta">
          <span className="plus-dot"><PlusIcon size={20} /></span>
          <span className="row__body">
            <span className="row__title">Add custom appliance</span>
            <span className="row__sub">Can’t find your appliance? Add it manually.</span>
          </span>
          <span className="row__end"><ChevronRight /></span>
        </Link>
      </section>
    </div>
  );
}
