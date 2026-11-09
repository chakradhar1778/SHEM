import { HeroScene, HillsBackdrop, type HeroVariant } from './HeroArt';

interface PageHeroProps {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  eyebrow?: string;
  art?: HeroVariant;
  /** 'wide' lets the title use the full width (art sits behind), 'split' leaves room for art on the right. */
  layout?: 'wide' | 'split';
  /** Replaces the illustrated scene with custom artwork (e.g. a category tile). */
  aside?: React.ReactNode;
  children?: React.ReactNode;
}

/** The big serif title over a soft illustrated scene — the opening of every main screen. */
export function PageHero({ title, subtitle, eyebrow, art = 'villa', layout = 'split', aside, children }: PageHeroProps) {
  return (
    <header className={`hero hero--${layout}`}>
      <div className="hero__art">
        <HillsBackdrop />
        <HeroScene variant={art} />
        {aside && <div className="hero__aside">{aside}</div>}
      </div>
      <div className="hero__text">
        {eyebrow && <span className="hero__eyebrow">{eyebrow}</span>}
        <h1 className="hero__title">{title}</h1>
        {subtitle && <p className="hero__subtitle">{subtitle}</p>}
        <span className="hero__rule" aria-hidden="true" />
        {children}
      </div>
    </header>
  );
}
