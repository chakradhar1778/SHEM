import type { TargetStatus } from '../../utils/targetEvaluation';

interface TargetHeroIllustrationProps {
  status?: TargetStatus;
  isEditMode?: boolean;
}

export function TargetHeroIllustration({ status = 'NOT_CONFIGURED', isEditMode = false }: TargetHeroIllustrationProps) {
  // Determine badge and ring accent styling based on status
  let badgeColor = '#3B82F6';
  let badgeBg = '#DBEAFE';
  let badgeIcon = (
    // Default lightning target icon (setup / neutral)
    <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" fill="#3B82F6" stroke="#2563EB" strokeWidth="1" />
  );

  if (!isEditMode) {
    if (status === 'WITHIN_TARGET') {
      badgeColor = '#16A34A';
      badgeBg = '#DCFCE7';
      badgeIcon = (
        // Leaf icon (matching Group 26.png)
        <path
          d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 3.3 17 3.3s-1.5 6.5-4.5 10.3A6.98 6.98 0 0 1 11 20z M2 21c0-4 3.5-7 7.5-7"
          fill="#16A34A"
          stroke="#15803D"
          strokeWidth="1.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      );
    } else if (status === 'ON_TRACK') {
      badgeColor = '#D97706';
      badgeBg = '#FEF3C7';
      badgeIcon = (
        // Lightning bolt icon (matching Group 27.png)
        <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" fill="#D97706" stroke="#B45309" strokeWidth="1" />
      );
    } else if (status === 'EXCEEDED_TARGET') {
      badgeColor = '#DC2626';
      badgeBg = '#FEE2E2';
      badgeIcon = (
        // Alert triangle icon (matching Red alert.png)
        <path
          d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z M12 9v4 M12 17h.01"
          fill="#DC2626"
          stroke="#FFFFFF"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      );
    }
  }

  return (
    <div className="target-hero" aria-hidden="true">
      <div className="target-hero__scene">
        {/* Soft Celestial Glow */}
        <div className="target-hero__sun" />

        {/* Rolling Hills Background */}
        <div className="target-hero__hills">
          <svg viewBox="0 0 380 150" preserveAspectRatio="none" className="target-hero__hills-svg">
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

        {/* Central Illustrated Home with Solar Roof & Dynamic Target Seal */}
        <div className="target-hero__house">
          <svg viewBox="0 0 260 180" width="240" height="166">
            <defs>
              <linearGradient id="thHouseWall" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#FFFFFF" />
                <stop offset="100%" stopColor="#F1F5F9" />
              </linearGradient>
              <linearGradient id="thRoofGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#2563EB" />
                <stop offset="100%" stopColor="#1E3A8A" />
              </linearGradient>
              <linearGradient id="thWarmWindow" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#FEF08A" />
                <stop offset="100%" stopColor="#F59E0B" />
              </linearGradient>
              <filter id="thGlow" x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur stdDeviation="3" result="blur" />
                <feComposite in="SourceGraphic" in2="blur" operator="over" />
              </filter>
            </defs>

            {/* Curving Winding Pathway */}
            <path
              d="M130 170 C125 155, 115 145, 130 135 C145 125, 135 110, 140 105"
              fill="none"
              stroke="#D5E4F3"
              strokeWidth="24"
              strokeLinecap="round"
            />
            <path
              d="M130 170 C125 155, 115 145, 130 135 C145 125, 135 110, 140 105"
              fill="none"
              stroke="#EEF4FA"
              strokeWidth="18"
              strokeLinecap="round"
            />

            {/* Trees & Foliage in Navy / Steel Blue tones */}
            <circle cx="50" cy="115" r="24" fill="#6B8CAE" opacity="0.8" />
            <circle cx="70" cy="125" r="20" fill="#52789C" opacity="0.85" />
            <circle cx="215" cy="118" r="22" fill="#52789C" opacity="0.85" />
            <circle cx="230" cy="130" r="18" fill="#6B8CAE" opacity="0.8" />

            {/* Target Status Floating Orb (Top Right) */}
            <g transform="translate(186, 32)">
              {/* Outer pulsing ring */}
              <circle cx="20" cy="20" r="28" fill="none" stroke={badgeColor} strokeWidth="1.5" strokeDasharray="3 3" opacity="0.4" />
              {/* Solid circular target backdrop */}
              <circle cx="20" cy="20" r="22" fill={badgeBg} stroke={badgeColor} strokeWidth="2.5" />
              {/* Inner symbol */}
              <g transform="translate(8, 8) scale(1)">
                {badgeIcon}
              </g>
            </g>

            {/* House Structure */}
            <rect x="80" y="86" width="96" height="66" rx="6" fill="url(#thHouseWall)" stroke="#CBD5E1" strokeWidth="1.2" />

            {/* Pitched Roof with Solar Panel Array */}
            <polygon points="128,42 68,88 188,88" fill="url(#thRoofGrad)" />
            {/* Solar panel grid lines */}
            <line x1="90" y1="84" x2="114" y2="52" stroke="#93C5FD" strokeWidth="1.5" opacity="0.75" />
            <line x1="110" y1="84" x2="126" y2="52" stroke="#93C5FD" strokeWidth="1.5" opacity="0.75" />
            <line x1="130" y1="84" x2="136" y2="52" stroke="#93C5FD" strokeWidth="1.5" opacity="0.75" />
            <line x1="150" y1="84" x2="146" y2="52" stroke="#93C5FD" strokeWidth="1.5" opacity="0.75" />
            <line x1="80" y1="72" x2="176" y2="72" stroke="#93C5FD" strokeWidth="1.5" opacity="0.75" />

            {/* Warm Windows with Soft Glow */}
            <rect x="94" y="98" width="18" height="20" rx="3" fill="url(#thWarmWindow)" filter="url(#thGlow)" />
            <line x1="103" y1="98" x2="103" y2="118" stroke="#122448" strokeWidth="0.8" opacity="0.6" />
            <line x1="94" y1="108" x2="112" y2="108" stroke="#122448" strokeWidth="0.8" opacity="0.6" />

            <rect x="144" y="98" width="18" height="20" rx="3" fill="url(#thWarmWindow)" filter="url(#thGlow)" />
            <line x1="153" y1="98" x2="153" y2="118" stroke="#122448" strokeWidth="0.8" opacity="0.6" />
            <line x1="144" y1="108" x2="162" y2="108" stroke="#122448" strokeWidth="0.8" opacity="0.6" />

            {/* Navy Front Door */}
            <rect x="120" y="112" width="16" height="40" rx="2" fill="#122448" />
            <circle cx="124" cy="132" r="1.5" fill="#F8FAFC" />
          </svg>
        </div>
      </div>
    </div>
  );
}
