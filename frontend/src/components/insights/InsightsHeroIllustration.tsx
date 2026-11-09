export function InsightsHeroIllustration() {
  return (
    <div className="insights-hero" aria-hidden="true">
      <div className="insights-hero__scene">
        {/* Soft Glowing Sun / Celestial Orb */}
        <div className="insights-hero__sun" />

        {/* Soft Watercolor Hill Layers */}
        <div className="insights-hero__hills">
          <svg viewBox="0 0 380 150" preserveAspectRatio="none" className="insights-hero__hills-svg">
            <path
              d="M-20 110 C 70 65, 170 120, 270 80 C 330 55, 380 85, 420 105 L 420 150 L -20 150 Z"
              fill="#DCE8F5"
              opacity="0.65"
            />
            <path
              d="M-20 90 C 80 40, 190 100, 290 60 C 340 45, 390 70, 420 90 L 420 150 L -20 150 Z"
              fill="#CCDFF2"
              opacity="0.75"
            />
            <path
              d="M-20 120 C 90 85, 200 125, 300 100 C 355 85, 390 110, 420 125 L 420 150 L -20 150 Z"
              fill="#EEF4FA"
            />
          </svg>
        </div>

        {/* Modern Illustrated Home with Energy Spline Waves */}
        <div className="insights-hero__house">
          <svg viewBox="0 0 260 170" width="240" height="156">
            <defs>
              <linearGradient id="ihWallGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#FFFFFF" />
                <stop offset="100%" stopColor="#F1F5F9" />
              </linearGradient>
              <linearGradient id="ihRoofGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#1E3A8A" />
                <stop offset="100%" stopColor="#0F172A" />
              </linearGradient>
              <linearGradient id="ihEnergyCurve" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#38BDF8" />
                <stop offset="50%" stopColor="#2563EB" />
                <stop offset="100%" stopColor="#1D4ED8" />
              </linearGradient>
              <linearGradient id="ihWarmLight" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#FEF08A" />
                <stop offset="100%" stopColor="#F59E0B" />
              </linearGradient>
              <filter id="ihGlow" x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur stdDeviation="3" result="blur" />
                <feComposite in="SourceGraphic" in2="blur" operator="over" />
              </filter>
            </defs>

            {/* Background Foliage in Steel Blue */}
            <circle cx="45" cy="115" r="26" fill="#6B8CAE" opacity="0.8" />
            <circle cx="68" cy="125" r="20" fill="#52789C" opacity="0.85" />
            <circle cx="215" cy="118" r="24" fill="#52789C" opacity="0.85" />
            <circle cx="235" cy="128" r="18" fill="#6B8CAE" opacity="0.8" />

            {/* Dynamic Energy Trend Wave Line wrapping into house (Group 12.png signature) */}
            <path
              d="M10 135 C60 145, 100 110, 140 85 C170 65, 200 70, 240 50"
              fill="none"
              stroke="url(#ihEnergyCurve)"
              strokeWidth="4"
              strokeLinecap="round"
            />
            {/* Glow under spline */}
            <path
              d="M10 135 C60 145, 100 110, 140 85 C170 65, 200 70, 240 50 L240 170 L10 170 Z"
              fill="url(#ihEnergyCurve)"
              opacity="0.08"
            />

            {/* Illustrated Home Body */}
            <rect x="90" y="82" width="86" height="64" rx="6" fill="url(#ihWallGrad)" stroke="#CBD5E1" strokeWidth="1.2" />

            {/* Pitched Roof */}
            <polygon points="133,40 76,84 190,84" fill="url(#ihRoofGrad)" />

            {/* Warm Glowing Windows */}
            <rect x="102" y="94" width="16" height="18" rx="3" fill="url(#ihWarmLight)" filter="url(#ihGlow)" />
            <rect x="146" y="94" width="16" height="18" rx="3" fill="url(#ihWarmLight)" filter="url(#ihGlow)" />

            {/* Navy Front Door */}
            <rect x="124" y="108" width="16" height="38" rx="2" fill="#122448" />
            <circle cx="127" cy="126" r="1.5" fill="#F8FAFC" />
          </svg>
        </div>
      </div>
    </div>
  );
}
