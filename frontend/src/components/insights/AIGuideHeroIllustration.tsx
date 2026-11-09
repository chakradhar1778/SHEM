export function AIGuideHeroIllustration() {
  return (
    <div className="guide-hero-illustration-container" aria-hidden="true">
      <svg
        viewBox="0 0 360 160"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="guide-hero-svg"
      >
        <defs>
          <linearGradient id="guideGlow" x1="180" y1="20" x2="180" y2="120" gradientUnits="userSpaceOnUse">
            <stop stopColor="#FDE047" stopOpacity="0.45" />
            <stop stopColor="#F59E0B" stopOpacity="0.1" />
            <stop stopColor="#F59E0B" stopOpacity="0" />
          </linearGradient>

          <linearGradient id="roofGrad" x1="140" y1="60" x2="220" y2="130" gradientUnits="userSpaceOnUse">
            <stop stopColor="#3B82F6" stopOpacity="0.15" />
            <stop stopColor="#1E3A8A" stopOpacity="0.05" />
          </linearGradient>
        </defs>

        {/* Ambient Warm Energy Glow */}
        <ellipse cx="180" cy="56" rx="64" ry="44" fill="url(#guideGlow)" />

        {/* Botanical Foliage Accents (Left and Right) */}
        <g stroke="#10B981" strokeWidth="1.2" strokeLinecap="round" opacity="0.6">
          <path d="M50 145 C52 125 64 115 80 110" />
          <path d="M62 130 C68 122 75 125 72 118" />
          <path d="M55 140 C50 132 46 134 48 126" />

          <path d="M310 145 C308 125 296 115 280 110" />
          <path d="M298 130 C292 122 285 125 288 118" />
          <path d="M305 140 C310 132 314 134 312 126" />
        </g>

        {/* Minimalist Modern Architectural Home Linework */}
        <g stroke="#1E293B" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" opacity="0.85">
          {/* Main Gable Roof */}
          <path d="M120 110 L180 62 L240 110" fill="url(#roofGrad)" />
          {/* House walls */}
          <line x1="134" y1="110" x2="134" y2="148" />
          <line x1="226" y1="110" x2="226" y2="148" />
          {/* Ground line */}
          <line x1="30" y1="148" x2="330" y2="148" stroke="#CBD5E1" strokeWidth="1.2" />

          {/* Window grid */}
          <rect x="146" y="118" width="24" height="20" rx="3" stroke="#3B82F6" strokeWidth="1.2" fill="#FFFFFF" />
          <line x1="158" y1="118" x2="158" y2="138" stroke="#93C5FD" strokeWidth="1" />
          <line x1="146" y1="128" x2="170" y2="128" stroke="#93C5FD" strokeWidth="1" />

          {/* Door */}
          <rect x="190" y="122" width="18" height="26" rx="2" stroke="#1E293B" strokeWidth="1.2" fill="#F1F5F9" />
          <circle cx="194" cy="135" r="1.2" fill="#1E293B" />
        </g>

        {/* Central Smart Glowing Bulb */}
        <g transform="translate(180, 48)">
          {/* Light Rays */}
          <line x1="0" y1="-26" x2="0" y2="-34" stroke="#F59E0B" strokeWidth="1.8" strokeLinecap="round" />
          <line x1="-20" y1="-18" x2="-26" y2="-24" stroke="#F59E0B" strokeWidth="1.8" strokeLinecap="round" />
          <line x1="20" y1="-18" x2="26" y2="-24" stroke="#F59E0B" strokeWidth="1.8" strokeLinecap="round" />
          <line x1="-24" y1="2" x2="-32" y2="2" stroke="#F59E0B" strokeWidth="1.8" strokeLinecap="round" />
          <line x1="24" y1="2" x2="32" y2="2" stroke="#F59E0B" strokeWidth="1.8" strokeLinecap="round" />

          {/* Bulb Outline and Filament */}
          <path
            d="M-14 -4 C-14 -14 -6 -20 0 -20 C6 -20 14 -14 14 -4 C14 2 10 7 8 10 L8 16 L-8 16 L-8 10 C-10 7 -14 2 -14 -4 Z"
            fill="#FEF08A"
            stroke="#D97706"
            strokeWidth="1.6"
            strokeLinejoin="round"
          />
          {/* Bulb screw base */}
          <path d="M-6 16 L6 16 L5 20 L-5 20 Z" fill="#94A3B8" stroke="#64748B" strokeWidth="1.2" />
          <line x1="-4" y1="18" x2="4" y2="18" stroke="#E2E8F0" strokeWidth="1" />

          {/* Internal Leaf / Eco Filament Icon */}
          <path
            d="M0 6 C-4 2 -5 -6 0 -12 C5 -6 4 2 0 6 Z"
            fill="#10B981"
            stroke="#059669"
            strokeWidth="0.8"
          />
        </g>
      </svg>
    </div>
  );
}
