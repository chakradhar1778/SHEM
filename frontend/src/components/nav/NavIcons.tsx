/** Navigation icons in the SHEM brush style (navy body, periwinkle sweep). */
const NAVY = '#1B2A5C';
const MID = '#6479BA';
const SOFT = '#B7C6E8';

export type NavIconName = 'home' | 'devices' | 'live' | 'bill' | 'target' | 'insights' | 'map';

export function NavIcon({ name, size = 26 }: { name: NavIconName; size?: number }) {
  const common = { viewBox: '0 0 48 48', width: size, height: size, fill: 'none', 'aria-hidden': true as const, focusable: false as const };
  switch (name) {
    case 'home':
      return (
        <svg {...common}>
          <path d="M3 24 24 5l21 19v4h-4v14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V28H3z" fill={NAVY} />
          <path d="M7 36c6-5 11-4 17-1s12 2 17-2v7a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2z" fill={SOFT} />
          <path d="M19 44V32a5 5 0 0 1 10 0v12z" fill="#fff" opacity=".95" />
        </svg>
      );
    case 'devices':
      return (
        <svg {...common}>
          <path d="M16 3h4v10h-4zM28 3h4v10h-4z" fill={NAVY} />
          <path d="M10 13h28v10c0 7-5 12-11 13v8h-6v-8c-6-1-11-6-11-13z" fill={NAVY} />
          <path d="M10 25c5-2 9 1 14 2s9 0 14-3c0 2-1 4-2 6-4 2-8 1-12 0s-9-1-13 1c-1-2-1-4-1-6z" fill={SOFT} />
        </svg>
      );
    case 'live':
      return (
        <svg {...common}>
          <circle cx="24" cy="24" r="19" fill="none" stroke={NAVY} strokeWidth="4" />
          <path d="M27 6 12 27h10l-3 15 17-23H26z" fill={MID} />
          <path d="M27 6 12 27h10l-2 8 8-17h-6z" fill={NAVY} />
        </svg>
      );
    case 'bill':
      return (
        <svg {...common}>
          <path d="M9 4h22l9 9v28a3 3 0 0 1-3 3H12a3 3 0 0 1-3-3z" fill={NAVY} />
          <path d="M31 4v9h9z" fill={SOFT} />
          <path d="M15 22h18M15 28h14" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
          <path d="M9 38c6-3 11-2 16 0s10 2 15-1v4a3 3 0 0 1-3 3H12a3 3 0 0 1-3-3z" fill={SOFT} />
        </svg>
      );
    case 'target':
      return (
        <svg {...common}>
          <circle cx="22" cy="26" r="18" fill={NAVY} />
          <circle cx="22" cy="26" r="12" fill="#EEF2FB" />
          <circle cx="22" cy="26" r="7" fill={NAVY} />
          <circle cx="22" cy="26" r="3" fill="#EEF2FB" />
          <path d="M23 25 41 7c2 6 0 9-4 11l-6 3z" fill={MID} />
        </svg>
      );
    case 'insights':
      return (
        <svg {...common}>
          <rect x="4" y="26" width="10" height="16" rx="3" fill={NAVY} />
          <rect x="19" y="16" width="10" height="26" rx="3" fill={NAVY} />
          <rect x="34" y="4" width="10" height="38" rx="3" fill={NAVY} />
          <path d="M4 38c5-4 9-4 14-7M19 34c4-3 7-4 10-8M34 24c3-2 6-3 10-5v7c-4 3-7 5-10 5z" stroke={SOFT} strokeWidth="2.6" strokeLinecap="round" opacity=".9" />
        </svg>
      );
    case 'map':
      return (
        <svg {...common}>
          <path d="M24 3C15 3 9 10 9 18c0 11 15 27 15 27s15-16 15-27C39 10 33 3 24 3z" fill={NAVY} />
          <path d="M9 26c5-3 9-1 14 0s11 1 16-4c-1 4-4 10-8 15-7-3-12-5-22-3z" fill={SOFT} opacity=".9" />
          <circle cx="24" cy="18" r="6" fill="#fff" />
        </svg>
      );
  }
}

/** SHEM wave logo mark. */
export function ShemLogo({ size = 30 }: { size?: number }) {
  return (
    <svg viewBox="0 0 48 32" width={size * 1.5} height={size} fill="none" aria-hidden="true" focusable="false">
      <path d="M2 14c8-8 18-9 30-5 5 2 9 2 14 0-3 6-8 9-14 8-8-2-15 0-24 7-3 1-4-5-6-10z" fill={NAVY} />
      <path d="M4 24c7-5 14-5 22-2 6 2 12 2 18-1-3 6-9 9-16 8-8-1-13 1-19 5-3 0-4-6-5-10z" fill={MID} />
    </svg>
  );
}
