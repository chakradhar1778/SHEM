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

/** SHEM wave logo mark - recreated exact vector match from brand specification. */
export function ShemLogo({ size = 30, className = '' }: { size?: number; className?: string }) {
  return (
    <svg
      viewBox="0 0 375 255"
      width={Math.round(size * 1.47)}
      height={size}
      fill="none"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      <defs>
        <linearGradient id="shemTopWing" x1="0%" y1="0%" x2="100%" y2="60%">
          <stop offset="0%" stopColor="#6981b0" />
          <stop offset="45%" stopColor="#486295" />
          <stop offset="100%" stopColor="#324776" />
        </linearGradient>
        <linearGradient id="shemMidRibbon" x1="0%" y1="50%" x2="100%" y2="50%">
          <stop offset="0%" stopColor="#05184e" />
          <stop offset="50%" stopColor="#010e39" />
          <stop offset="100%" stopColor="#05184e" />
        </linearGradient>
        <linearGradient id="shemBotWing" x1="100%" y1="100%" x2="0%" y2="40%">
          <stop offset="0%" stopColor="#6981b0" />
          <stop offset="45%" stopColor="#486295" />
          <stop offset="100%" stopColor="#324776" />
        </linearGradient>
        <linearGradient id="shemGloss" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.25" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d="M 100.0 108.0 C 100.2 108.2, 98.7 110.0, 101.0 109.0 C 103.3 108.0, 109.3 104.0, 114.0 102.0 C 118.7 100.0, 124.7 98.2, 129.0 97.0 C 133.3 95.8, 134.7 95.3, 140.0 95.0 C 145.3 94.7, 153.8 94.0, 161.0 95.0 C 168.2 96.0, 174.8 97.8, 183.0 101.0 C 191.2 104.2, 202.2 110.8, 210.0 114.0 C 217.8 117.2, 223.0 118.8, 230.0 120.0 C 237.0 121.2, 246.5 121.2, 252.0 121.0 C 257.5 120.8, 258.3 120.3, 263.0 119.0 C 267.7 117.7, 273.0 116.8, 280.0 113.0 C 287.0 109.2, 298.0 101.8, 305.0 96.0 C 312.0 90.2, 316.8 84.7, 322.0 78.0 C 327.2 71.3, 333.7 59.7, 336.0 56.0 C 335.8 55.8, 338.3 53.3, 335.0 55.0 C 331.7 56.7, 321.8 63.2, 316.0 66.0 C 310.2 68.8, 304.3 70.7, 300.0 72.0 C 295.7 73.3, 294.7 73.7, 290.0 74.0 C 285.3 74.3, 278.5 74.8, 272.0 74.0 C 265.5 73.2, 257.8 71.0, 251.0 69.0 C 244.2 67.0, 235.2 63.7, 231.0 62.0 C 226.8 60.3, 227.3 59.5, 226.0 59.0 C 224.7 58.5, 226.7 60.2, 223.0 59.0 C 219.3 57.8, 209.0 53.5, 204.0 52.0 C 199.0 50.5, 197.8 50.3, 193.0 50.0 C 188.2 49.7, 179.8 49.7, 175.0 50.0 C 170.2 50.3, 168.8 50.5, 164.0 52.0 C 159.2 53.5, 152.5 55.3, 146.0 59.0 C 139.5 62.7, 131.2 68.3, 125.0 74.0 C 118.8 79.7, 113.2 87.3, 109.0 93.0 C 104.8 98.7, 101.5 105.5, 100.0 108.0 Z" fill="url(#shemTopWing)" />
      <path d="M 185 50 C 225 66, 275 92, 336 56 C 300 73, 245 68, 185 50 Z" fill="url(#shemGloss)" />
      <path d="M 49.0 157.0 C 51.2 155.7, 56.7 151.7, 62.0 149.0 C 67.3 146.3, 74.8 143.0, 81.0 141.0 C 87.2 139.0, 92.7 137.8, 99.0 137.0 C 105.3 136.2, 111.0 135.5, 119.0 136.0 C 127.0 136.5, 137.3 137.5, 147.0 140.0 C 156.7 142.5, 167.7 148.0, 177.0 151.0 C 186.3 154.0, 196.5 156.5, 203.0 158.0 C 209.5 159.5, 208.8 159.8, 216.0 160.0 C 223.2 160.2, 238.2 160.0, 246.0 159.0 C 253.8 158.0, 257.0 156.7, 263.0 154.0 C 269.0 151.3, 276.2 147.3, 282.0 143.0 C 287.8 138.7, 293.0 133.7, 298.0 128.0 C 303.0 122.3, 309.7 112.2, 312.0 109.0 C 312.0 108.7, 314.3 105.7, 312.0 107.0 C 309.7 108.3, 303.0 114.0, 298.0 117.0 C 293.0 120.0, 287.0 122.8, 282.0 125.0 C 277.0 127.2, 273.0 128.7, 268.0 130.0 C 263.0 131.3, 257.3 132.5, 252.0 133.0 C 246.7 133.5, 242.0 133.7, 236.0 133.0 C 230.0 132.3, 223.0 131.0, 216.0 129.0 C 209.0 127.0, 198.8 123.0, 194.0 121.0 C 189.2 119.0, 188.7 117.7, 187.0 117.0 C 185.3 116.3, 185.3 117.5, 184.0 117.0 C 182.7 116.5, 182.7 115.3, 179.0 114.0 C 175.3 112.7, 166.7 110.2, 162.0 109.0 C 157.3 107.8, 157.3 107.3, 151.0 107.0 C 144.7 106.7, 132.3 106.0, 124.0 107.0 C 115.7 108.0, 108.3 110.2, 101.0 113.0 C 93.7 115.8, 87.2 118.8, 80.0 124.0 C 72.8 129.2, 63.2 138.5, 58.0 144.0 C 52.8 149.5, 50.5 154.8, 49.0 157.0 Z" fill="url(#shemMidRibbon)" />
      <path d="M 34.0 208.0 C 35.7 206.7, 39.8 202.8, 44.0 200.0 C 48.2 197.2, 54.3 193.3, 59.0 191.0 C 63.7 188.7, 67.3 187.3, 72.0 186.0 C 76.7 184.7, 81.5 183.5, 87.0 183.0 C 92.5 182.5, 99.7 182.5, 105.0 183.0 C 110.3 183.5, 114.8 184.8, 119.0 186.0 C 123.2 187.2, 124.7 187.5, 130.0 190.0 C 135.3 192.5, 144.0 198.0, 151.0 201.0 C 158.0 204.0, 167.3 206.7, 172.0 208.0 C 176.7 209.3, 174.0 209.0, 179.0 209.0 C 184.0 209.0, 195.5 209.0, 202.0 208.0 C 208.5 207.0, 212.3 205.5, 218.0 203.0 C 223.7 200.5, 229.7 197.7, 236.0 193.0 C 242.3 188.3, 250.7 180.7, 256.0 175.0 C 261.3 169.3, 266.0 161.7, 268.0 159.0 C 268.0 158.7, 269.5 156.5, 268.0 157.0 C 266.5 157.5, 264.0 160.2, 259.0 162.0 C 254.0 163.8, 245.5 167.0, 238.0 168.0 C 230.5 169.0, 221.5 169.0, 214.0 168.0 C 206.5 167.0, 199.3 164.3, 193.0 162.0 C 186.7 159.7, 182.7 156.7, 176.0 154.0 C 169.3 151.3, 158.8 147.7, 153.0 146.0 C 147.2 144.3, 147.7 144.2, 141.0 144.0 C 134.3 143.8, 120.7 143.8, 113.0 145.0 C 105.3 146.2, 99.7 149.2, 95.0 151.0 C 90.3 152.8, 89.3 153.3, 85.0 156.0 C 80.7 158.7, 75.2 161.8, 69.0 167.0 C 62.8 172.2, 53.8 180.2, 48.0 187.0 C 42.2 193.8, 36.3 204.5, 34.0 208.0 Z" fill="url(#shemBotWing)" />
      <path d="M 190 209 C 150 193, 100 167, 34 204 C 70 187, 130 192, 190 209 Z" fill="url(#shemGloss)" />
    </svg>
  );
}
