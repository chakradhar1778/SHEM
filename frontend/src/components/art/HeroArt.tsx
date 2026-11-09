import { ApplianceIcon } from '../appliances/ApplianceIcons';

/**
 * Illustrated hero scenes in the SHEM style: layered pale-blue hills, a soft sun,
 * navy foliage and a warm lit home. Pure SVG so they scale and can be replaced by
 * client artwork without touching the screens.
 */

const NAVY = '#1B2A5C';
const MID = '#6479BA';
const SOFT = '#B7C6E8';
const MIST = '#DCE6F6';
const CREAM = '#FBF6EA';
const WARM = '#FBE3A0';

export type HeroVariant = 'blocks' | 'villa' | 'cottage' | 'room' | 'bill' | 'story';

function Leaf({ x, y, r = 0, s = 1, c = NAVY }: { x: number; y: number; r?: number; s?: number; c?: string }) {
  return (
    <path
      transform={`translate(${x} ${y}) rotate(${r}) scale(${s})`}
      d="M0 0C-9-10-8-26 0-38 8-26 9-10 0 0z"
      fill={c}
    />
  );
}

function Tree({ x, y, s = 1, c = NAVY }: { x: number; y: number; s?: number; c?: string }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <path d="M0 0v-18" stroke={NAVY} strokeWidth="2.4" strokeLinecap="round" />
      <ellipse cx="0" cy="-30" rx="13" ry="20" fill={c} />
      <path d="M-4-42c-6 8-6 18 0 26" stroke={SOFT} strokeWidth="2" strokeLinecap="round" opacity=".6" />
    </g>
  );
}

/** Full-width pale hills and sun that sit behind every hero scene. */
export function HillsBackdrop() {
  return (
    <svg viewBox="0 0 430 300" preserveAspectRatio="none" className="hero__hills" aria-hidden="true" focusable="false">
      <circle cx="338" cy="70" r="34" fill="#FBEBB5" opacity=".8" />
      <path d="M0 150c60-46 120-52 190-24 52 21 96 8 140-16 40-22 76-18 100 2v188H0z" fill={MIST} opacity=".95" />
      <path d="M0 190c70-30 140-34 206-12 56 18 106 10 148-6 28-10 52-8 76 2v126H0z" fill={SOFT} opacity=".5" />
      <path d="M0 236c80-22 170-24 250-4 70 18 130 10 180-6v74H0z" fill="#fff" opacity=".95" />
    </svg>
  );
}

function FloatingTile({ x, y, icon, size = 40 }: { x: number; y: number; icon: string; size?: number }) {
  return (
    <foreignObject x={x} y={y} width={size} height={size}>
      <div
        style={{
          width: size,
          height: size,
          borderRadius: 12,
          background: 'linear-gradient(145deg,#FFFDF6,#F2ECDC)',
          boxShadow: '0 6px 14px rgba(27,42,92,.14), inset 0 1px 0 #fff',
          display: 'grid',
          placeItems: 'center',
        }}
      >
        <ApplianceIcon type={icon} size={size * 0.62} />
      </div>
    </foreignObject>
  );
}

function Blocks() {
  return (
    <>
      <path
        d="M70 80c30-24 60-24 90 0M100 80c0-14 8-24 14-24M84 56c14-12 28-12 40-4"
        stroke={MID}
        strokeWidth="1.2"
        strokeDasharray="2 4"
        fill="none"
      />
      <g>
        <rect x="76" y="118" width="108" height="64" rx="12" fill="#F4F0E6" />
        <rect x="94" y="84" width="76" height="48" rx="12" fill="#ECE8DE" />
        <rect x="112" y="68" width="48" height="36" rx="10" fill="#F8F4EA" />
        <path d="M94 100l42-30 34 28z" fill={NAVY} />
        <path d="M76 138l40-22v40z" fill={NAVY} />
        <path d="M144 132h40v50h-40z" fill="#E4E0D6" />
        <path d="M84 182v-26a16 16 0 0132 0v26z" fill={NAVY} />
        <path d="M92 182v-20a8 8 0 0116 0v20z" fill={WARM} />
        <path d="M150 182v-22a8 8 0 0116 0v22z" fill={NAVY} opacity=".85" />
      </g>
      <FloatingTile x={34} y={52} icon="bulb" />
      <FloatingTile x={114} y={12} icon="fan" />
      <FloatingTile x={184} y={52} icon="ac" />
      <Leaf x={62} y={184} r={-24} s={1.1} c={MID} />
      <Leaf x={52} y={184} r={-48} s={0.9} />
      <Leaf x={198} y={184} r={28} s={1.1} c={MID} />
      <Leaf x={210} y={184} r={50} s={0.9} />
    </>
  );
}

function Villa() {
  return (
    <>
      <path d="M30 128h194v54H30z" fill="#F7F4EC" />
      <path d="M52 92h96v40H52z" fill="#FFFFFF" />
      <path d="M40 124h210v8H40z" fill={NAVY} />
      <path d="M48 88h108v8H48z" fill={NAVY} />
      <rect x="62" y="98" width="30" height="24" rx="2" fill={WARM} />
      <rect x="98" y="98" width="42" height="24" rx="2" fill="#F5D88A" />
      <path d="M62 98h30M98 98h42" stroke="#fff" strokeWidth="2" />
      <rect x="40" y="138" width="58" height="36" rx="2" fill={WARM} />
      <rect x="106" y="138" width="40" height="36" rx="2" fill="#F5D88A" />
      <rect x="154" y="138" width="60" height="36" rx="2" fill="#DFE8F7" />
      <path d="M69 138v36M154 138v36M184 138v36" stroke="#fff" strokeWidth="2.4" />
      <path d="M52 182h170" stroke={SOFT} strokeWidth="2" />
      <Tree x={22} y={182} s={1.1} />
      <Tree x={238} y={182} s={1.2} c={MID} />
      <Leaf x={14} y={186} r={-30} s={0.9} c={MID} />
      <Leaf x={252} y={186} r={30} s={0.8} />
    </>
  );
}

function Cottage() {
  return (
    <>
      <path d="M44 86 128 30l84 56z" fill={NAVY} />
      <path d="M64 86 128 44l56 38z" fill="#2B3F82" opacity=".6" />
      <rect x="168" y="38" width="14" height="26" rx="2" fill={NAVY} />
      <rect x="62" y="86" width="132" height="86" rx="4" fill={CREAM} />
      <rect x="76" y="100" width="30" height="30" rx="3" fill={WARM} stroke={MID} strokeWidth="2" />
      <rect x="150" y="100" width="30" height="30" rx="3" fill={WARM} stroke={MID} strokeWidth="2" />
      <path d="M91 100v30M76 115h30M165 100v30M150 115h30" stroke={MID} strokeWidth="1.4" />
      <path d="M112 172v-44a16 16 0 0132 0v44z" fill={NAVY} />
      <circle cx="136" cy="152" r="2" fill={WARM} />
      <Tree x={36} y={176} s={1.25} />
      <Tree x={226} y={176} s={1.35} c={MID} />
      <Leaf x={52} y={180} r={-24} s={1} c={MID} />
      <Leaf x={206} y={180} r={26} s={1} />
    </>
  );
}

function Room() {
  return (
    <>
      <path d="M156 0v34" stroke={NAVY} strokeWidth="2" />
      <path d="M138 56c0-14 8-22 18-22s18 8 18 22z" fill={NAVY} />
      <path d="M146 54c1-8 5-12 10-12" stroke={SOFT} strokeWidth="2" strokeLinecap="round" />
      <ellipse cx="156" cy="60" rx="14" ry="5" fill={WARM} opacity=".8" />
      <path d="M196 182v-70a34 34 0 0168 0v70z" fill={WARM} opacity=".7" />
      <path d="M204 182v-62a26 26 0 0152 0v62z" fill="#F7EDCB" />
      <rect x="102" y="140" width="76" height="42" rx="10" fill={NAVY} />
      <rect x="96" y="128" width="88" height="26" rx="12" fill="#2B3F82" />
      <path d="M32 182c-4-26 6-46 22-60 4 14 2 36-4 60z" fill={NAVY} />
      <path d="M52 182c-2-30 8-52 26-64 3 20 0 44-8 64z" fill={MID} />
      <Leaf x={40} y={178} r={-30} s={1.2} c={MID} />
      <rect x="40" y="168" width="34" height="18" rx="5" fill={CREAM} />
    </>
  );
}

function Bill() {
  return (
    <>
      <g transform="rotate(8 150 100)">
        <rect x="96" y="22" width="104" height="132" rx="10" fill="#fff" stroke={SOFT} strokeWidth="1.6" />
        <circle cx="148" cy="54" r="15" fill={NAVY} />
        <path d="M152 42l-9 14h7l-3 10 11-15h-7z" fill={WARM} />
        <path d="M112 84h72M112 96h56M112 108h64" stroke={SOFT} strokeWidth="3" strokeLinecap="round" />
        <text x="148" y="140" textAnchor="middle" fontSize="22" fontWeight="700" fill={NAVY}>
          ₹
        </text>
      </g>
      <Leaf x={86} y={170} r={-24} s={1.3} />
      <Leaf x={74} y={170} r={-52} s={1} c={MID} />
      <Leaf x={218} y={170} r={22} s={1.3} c={MID} />
      <Leaf x={232} y={170} r={46} s={1} />
    </>
  );
}

function Story() {
  return (
    <>
      <Leaf x={60} y={184} r={-20} s={1.6} />
      <Leaf x={44} y={184} r={-44} s={1.3} c={MID} />
      <Leaf x={92} y={184} r={14} s={1.4} c={MID} />
      <Leaf x={216} y={184} r={22} s={1.7} />
      <Leaf x={234} y={184} r={46} s={1.3} c={MID} />
      <Leaf x={196} y={184} r={-8} s={1.4} c={MID} />
      <path d="M76 100 128 62l52 38z" fill={NAVY} />
      <rect x="88" y="100" width="80" height="62" rx="3" fill={CREAM} />
      <rect x="96" y="112" width="22" height="22" rx="2" fill={WARM} stroke={MID} strokeWidth="1.6" />
      <path d="M118 162v-24a10 10 0 0120 0v24z" fill={NAVY} />
    </>
  );
}

const SCENES: Record<HeroVariant, () => React.ReactElement> = {
  blocks: Blocks,
  villa: Villa,
  cottage: Cottage,
  room: Room,
  bill: Bill,
  story: Story,
};

export function HeroScene({ variant }: { variant: HeroVariant }) {
  const Scene = SCENES[variant];
  return (
    <svg viewBox="0 0 260 200" className="hero__svg" aria-hidden="true" focusable="false" preserveAspectRatio="xMidYMax meet">
      <Scene />
    </svg>
  );
}
