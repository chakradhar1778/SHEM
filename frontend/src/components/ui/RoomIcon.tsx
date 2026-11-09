const NAVY = '#1B2A5C';
const SOFT = '#B7C6E8';

export type RoomKind = 'bed' | 'bath' | 'dining' | 'kitchen' | 'utility' | 'closet' | 'balcony' | 'living' | 'home';

/** Pick a room glyph from the room name / type. */
export function roomKind(name: string): RoomKind {
  const n = name.toLowerCase();
  if (/bed|guest/.test(n)) return 'bed';
  if (/bath|toilet|wash ?room/.test(n)) return 'bath';
  if (/din/.test(n)) return 'dining';
  if (/kitchen/.test(n)) return 'kitchen';
  if (/util|laundry/.test(n)) return 'utility';
  if (/closet|wardrobe|dress/.test(n)) return 'closet';
  if (/balcon|terrace|garden/.test(n)) return 'balcony';
  if (/living|hall|lounge/.test(n)) return 'living';
  return 'home';
}

export function RoomIcon({ name, size = 28 }: { name: string; size?: number }) {
  const kind = roomKind(name);
  const p = { viewBox: '0 0 32 32', width: size, height: size, fill: 'none', 'aria-hidden': true as const, focusable: false as const };
  switch (kind) {
    case 'bed':
      return (<svg {...p}><rect x="3" y="14" width="26" height="9" rx="3" fill={NAVY} /><rect x="3" y="8" width="5" height="16" rx="2" fill={NAVY} /><rect x="10" y="10" width="10" height="5" rx="2" fill={SOFT} /><path d="M3 25v2M29 25v2" stroke={NAVY} strokeWidth="2.4" strokeLinecap="round" /></svg>);
    case 'bath':
      return (<svg {...p}><path d="M4 15h24v3a7 7 0 01-7 7H11a7 7 0 01-7-7z" fill={NAVY} /><path d="M8 15V8a3 3 0 016 0" stroke={NAVY} strokeWidth="2.4" strokeLinecap="round" /><path d="M9 26l-1 3M23 26l1 3" stroke={NAVY} strokeWidth="2.4" strokeLinecap="round" /><path d="M8 19c4 2 9 2 14 0" stroke={SOFT} strokeWidth="2" strokeLinecap="round" /></svg>);
    case 'dining':
      return (<svg {...p}><rect x="4" y="12" width="24" height="5" rx="2.5" fill={NAVY} /><path d="M8 17v10M24 17v10" stroke={NAVY} strokeWidth="2.6" strokeLinecap="round" /><path d="M10 8h4M18 8h4" stroke={SOFT} strokeWidth="3" strokeLinecap="round" /></svg>);
    case 'kitchen':
      return (<svg {...p}><path d="M6 14h20c0 8-4 12-10 12S6 22 6 14z" fill={NAVY} /><path d="M2 14h4M26 14h4" stroke={NAVY} strokeWidth="2.4" strokeLinecap="round" /><path d="M12 10c-2-2 2-3 0-6M18 10c-2-2 2-3 0-6" stroke={SOFT} strokeWidth="2" strokeLinecap="round" /></svg>);
    case 'utility':
      return (<svg {...p}><rect x="5" y="3" width="22" height="26" rx="4" fill={NAVY} /><circle cx="16" cy="18" r="7" fill="#EEF2FB" /><circle cx="16" cy="18" r="4" fill={SOFT} /><circle cx="10" cy="8" r="1.4" fill={SOFT} /></svg>);
    case 'closet':
      return (<svg {...p}><path d="M16 5a2.6 2.6 0 112.6 2.6L16 10 3 22a2 2 0 001.4 3.4h23.2A2 2 0 0029 22L16 10" stroke={NAVY} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" /></svg>);
    case 'balcony':
      return (<svg {...p}><path d="M9 29l-1-9h16l-1 9z" fill={NAVY} /><path d="M16 20c-6-1-8-6-6-12 5 1 7 5 6 12z" fill={NAVY} /><path d="M16 20c6-1 8-6 6-12-5 1-7 5-6 12z" fill={SOFT} /></svg>);
    case 'living':
      return (<svg {...p}><rect x="4" y="13" width="24" height="10" rx="4" fill={NAVY} /><rect x="2" y="15" width="6" height="10" rx="3" fill={NAVY} /><rect x="24" y="15" width="6" height="10" rx="3" fill={NAVY} /><rect x="9" y="8" width="14" height="7" rx="3" fill={SOFT} /></svg>);
    default:
      return (<svg {...p}><path d="M3 15 16 4l13 11M6 13v14h20V13" stroke={NAVY} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" /><path d="M13 27v-8h6v8" fill={SOFT} /></svg>);
  }
}
