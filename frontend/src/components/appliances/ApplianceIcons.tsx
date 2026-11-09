/**
 * SHEM hand-drawn style icons: a deep-navy body with a soft periwinkle "brush" sweep.
 * All icons share one 48x48 grid so they can be swapped for client artwork later.
 */
const NAVY = '#1B2A5C';
const MID = '#6479BA';
const SOFT = '#B7C6E8';
const MIST = '#E6ECF8';

interface IconProps {
  size?: number;
}

function Svg({ size = 24, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg viewBox="0 0 48 48" width={size} height={size} fill="none" aria-hidden="true" focusable="false">
      {children}
    </svg>
  );
}

const Bulb = (p: IconProps) => (
  <Svg {...p}>
    <path d="M24 3C17 11 12 17 12 25c0 6 4.5 10 12 15 7.5-5 12-9 12-15 0-8-5-14-12-22z" fill={NAVY} />
    <path d="M24 9c-4 6-6 10-6 15 0 4 2 7 6 10 0-6 2-9 5-13 2-3 1-7-5-12z" fill={SOFT} opacity=".85" />
    <path d="M24 16c-2 4-3 7-3 10s1 5 3 7" stroke={MIST} strokeWidth="1.6" strokeLinecap="round" />
    <rect x="18" y="40" width="12" height="3.2" rx="1.6" fill={NAVY} />
    <rect x="20" y="44" width="8" height="2.4" rx="1.2" fill={MID} />
  </Svg>
);

const Tube = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 17c8-6 16-2 24-6 6-3 11-2 14 0-3 6-9 5-16 8-8 4-15 7-22 3z" fill={NAVY} />
    <path d="M5 28c9-5 17-1 26-5 5-2 9-1 12 1-3 5-9 4-16 7-8 3-15 6-22 2z" fill={MID} />
    <path d="M7 38c8-4 15 0 23-3 5-2 8-1 11 1" stroke={SOFT} strokeWidth="3.2" strokeLinecap="round" />
  </Svg>
);

const Cfl = (p: IconProps) => (
  <Svg {...p}>
    <path d="M17 36c-2-8-1-12 3-14 4-1 8-2 8-6S25 8 24 6c6 1 10 5 10 10 0 5-4 6-6 9-2 3-1 7-4 11z" fill={NAVY} />
    <path d="M18 22c4 1 9 1 13-1M17 28c5 1 9 1 14-1M19 15c3 1 7 1 10-1" stroke={SOFT} strokeWidth="2.2" strokeLinecap="round" />
    <rect x="17" y="37" width="14" height="3.4" rx="1.7" fill={NAVY} />
    <rect x="19.5" y="41.4" width="9" height="2.8" rx="1.4" fill={MID} />
  </Svg>
);

const Lamp = (p: IconProps) => (
  <Svg {...p}>
    <path d="M24 3v10" stroke={NAVY} strokeWidth="2.4" strokeLinecap="round" />
    <path d="M7 31c0-11 7-18 17-18s17 7 17 18z" fill={NAVY} />
    <path d="M11 29c1-8 6-12 13-13 3 0 3 3-1 4-5 2-8 5-9 9z" fill={SOFT} opacity=".8" />
    <path d="M16 36l-3 6M24 34v9M32 36l3 6" stroke={MID} strokeWidth="2.4" strokeLinecap="round" />
  </Svg>
);

const Fan = (p: IconProps) => (
  <Svg {...p}>
    <path d="M24 22C16 20 10 12 15 7c5-4 12 3 9 15z" fill={NAVY} />
    <path d="M26 24c1-8 9-14 14-9 4 5-3 12-14 9z" fill={MID} />
    <path d="M22 26c-1 8-9 14-14 9-4-5 3-12 14-9z" fill={MID} />
    <path d="M24 26c8 2 14 9 9 14-5 4-12-3-9-14z" fill={NAVY} />
    <path d="M17 9c3 0 5 3 5 8" stroke={SOFT} strokeWidth="1.8" strokeLinecap="round" />
    <circle cx="24" cy="24" r="3.6" fill={MIST} stroke={NAVY} strokeWidth="2" />
  </Svg>
);

const Ac = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 30c6-1 12-8 20-14 7-5 15-5 22-3-2 4-6 6-12 9-8 4-15 9-30 8z" fill={NAVY} />
    <path d="M3 37c9 0 15-5 23-9 7-3 14-3 19-1-3 4-8 6-15 8-9 3-17 5-27 2z" fill={MID} />
    <path d="M5 43c8 0 15-3 22-5 6-1 11-1 15 0" stroke={SOFT} strokeWidth="3" strokeLinecap="round" />
  </Svg>
);

const Fridge = (p: IconProps) => (
  <Svg {...p}>
    <rect x="12" y="3" width="24" height="42" rx="6" fill={NAVY} />
    <path d="M12 17h24" stroke={MIST} strokeWidth="1.6" />
    <path d="M30 9c-4 2-6 6-6 12 0 6-1 10-6 14 6 0 11-3 14-9 3-6 2-13-2-17z" fill={SOFT} opacity=".85" />
    <path d="M17 9v4M17 22v7" stroke={MIST} strokeWidth="2" strokeLinecap="round" />
  </Svg>
);

const Pot = (p: IconProps) => (
  <Svg {...p}>
    <path d="M16 15c-3-3 3-5 0-9M23 14c-3-3 3-5 0-9" stroke={NAVY} strokeWidth="2.2" strokeLinecap="round" />
    <path d="M10 22h28c0 9-5 15-14 15S10 31 10 22z" fill={NAVY} />
    <path d="M13 24h22c-1 4-4 7-9 8-5 0-9-3-13-8z" fill={SOFT} opacity=".7" />
    <path d="M4 22h6M38 22h6" stroke={NAVY} strokeWidth="2.6" strokeLinecap="round" />
    <path d="M16 41h16" stroke={MID} strokeWidth="2.6" strokeLinecap="round" />
  </Svg>
);

const Tv = (p: IconProps) => (
  <Svg {...p}>
    <rect x="4" y="8" width="40" height="27" rx="6" fill={NAVY} />
    <path d="M8 29c3-8 9-14 17-15 7-1 11 1 15 5v10c-8 0-14-2-20 2-4 2-8 2-12-2z" fill={MIST} opacity=".92" />
    <path d="M10 27c4-6 9-9 16-10" stroke={SOFT} strokeWidth="2.2" strokeLinecap="round" />
    <path d="M16 42h16" stroke={NAVY} strokeWidth="3" strokeLinecap="round" />
    <path d="M24 35v7" stroke={NAVY} strokeWidth="3" />
  </Svg>
);

const Heater = (p: IconProps) => (
  <Svg {...p}>
    <path d="M24 3c-6 8-10 13-10 21 0 6 4 10 10 14 6-4 10-8 10-14 0-8-4-13-10-21z" fill={NAVY} />
    <path d="M24 12c-3 5-5 8-5 12 0 3 2 6 5 8 0-5 2-8 5-11 2-3 1-5-5-9z" fill={SOFT} opacity=".85" />
    <path d="M24 20c-1 3-2 5-2 7" stroke={MIST} strokeWidth="1.6" strokeLinecap="round" />
    <rect x="17" y="40" width="14" height="3.4" rx="1.7" fill={NAVY} />
  </Svg>
);

const Washer = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="24" cy="24" r="20" fill={NAVY} />
    <circle cx="24" cy="24" r="14" fill={MIST} />
    <path d="M10 25c3-6 8-6 12-2 4 4 9 3 12-2 1 6-2 13-10 14-7 1-12-4-14-10z" fill={MID} />
    <path d="M12 21c4-4 9-3 13 0" stroke={SOFT} strokeWidth="2.2" strokeLinecap="round" />
    <circle cx="11" cy="9" r="1.6" fill={SOFT} />
    <circle cx="16" cy="7" r="1.6" fill={SOFT} />
  </Svg>
);

const Microwave = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="10" width="34" height="28" rx="6" fill={NAVY} />
    <path d="M7 31c3-7 9-10 17-10 5 0 9 1 9 4v8c-8-1-13 2-19 2-4 0-6-1-7-4z" fill={MIST} opacity=".92" />
    <path d="M9 28c4-4 9-6 15-6" stroke={SOFT} strokeWidth="2.2" strokeLinecap="round" />
    <circle cx="42" cy="16" r="2.6" fill={NAVY} />
    <circle cx="42" cy="24" r="2.6" fill={NAVY} />
    <circle cx="42" cy="32" r="2.6" fill={NAVY} />
  </Svg>
);

const Mixer = (p: IconProps) => (
  <Svg {...p}>
    <path d="M18 4h12l2 4v10H16V8z" fill={NAVY} />
    <path d="M32 9c6 1 9 5 8 12" stroke={NAVY} strokeWidth="2.6" strokeLinecap="round" />
    <path d="M12 20h24c3 5 4 11 3 17 0 4-3 7-7 7H16c-4 0-7-3-7-7 0-6 1-12 3-17z" fill={NAVY} />
    <circle cx="23" cy="33" r="6" fill={MIST} />
    <circle cx="23" cy="33" r="2.6" fill={MID} />
    <path d="M14 26c4-2 8-2 13-1" stroke={SOFT} strokeWidth="2" strokeLinecap="round" />
  </Svg>
);

const Purifier = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 44V16C12 8 17 4 25 4c7 0 11 4 11 10v30H12z" fill={NAVY} />
    <path d="M17 12c3-3 8-4 13-2" stroke={SOFT} strokeWidth="2.4" strokeLinecap="round" />
    <path d="M22 28c-3 4-4 6-4 8a4 4 0 008 0c0-2-1-4-4-8z" fill={SOFT} />
    <path d="M32 33c-2 2-3 4-3 5a3 3 0 006 0c0-1-1-3-3-5z" fill={MID} />
  </Svg>
);

const Dishwasher = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 26C4 14 13 6 24 6s20 8 20 20v6H4z" fill={NAVY} />
    <path d="M10 26c0-8 6-13 14-13s14 5 14 13z" fill={MIST} />
    <path d="M14 26c0-5 4-8 10-8s10 3 10 8z" fill={SOFT} />
    <circle cx="24" cy="24" r="5" fill="#fff" />
    <path d="M4 34c7 2 11 6 20 6s14-4 20-6v4c-6 4-12 6-20 6s-14-2-20-6z" fill={MID} />
  </Svg>
);

const Fallback = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="24" cy="24" r="19" fill={NAVY} />
    <path d="M24 14v20M14 24h20" stroke={MIST} strokeWidth="3.2" strokeLinecap="round" />
  </Svg>
);

const ICONS: Record<string, (p: IconProps) => React.ReactElement> = {
  bulb: Bulb,
  tube: Tube,
  cfl: Cfl,
  lamp: Lamp,
  fan: Fan,
  ac: Ac,
  fridge: Fridge,
  pot: Pot,
  tv: Tv,
  heater: Heater,
  washer: Washer,
  microwave: Microwave,
  mixer: Mixer,
  purifier: Purifier,
  dishwasher: Dishwasher,
};

export function ApplianceIcon({ type, size = 24 }: { type: string; size?: number }) {
  const Icon = ICONS[type] ?? Fallback;
  return <Icon size={size} />;
}
