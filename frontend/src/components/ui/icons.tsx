/** Small line icons used inside UI chrome (rows, buttons, tiles). */
interface P {
  size?: number;
  className?: string;
}

function Line({ size = 20, className, children }: P & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export const ArrowIcon = (p: P) => <Line size={18} {...p}><path d="M5 12h14M13 6l6 6-6 6" /></Line>;
export const ChevronRight = (p: P) => <Line size={16} {...p}><path d="M9 6l6 6-6 6" /></Line>;
export const ChevronLeft = (p: P) => <Line size={16} {...p}><path d="M15 6l-6 6 6 6" /></Line>;
export const ChevronDown = (p: P) => <Line size={18} {...p}><path d="M6 9l6 6 6-6" /></Line>;
export const PlusIcon = (p: P) => <Line {...p}><path d="M12 5v14M5 12h14" /></Line>;
export const EditIcon = (p: P) => <Line size={16} {...p}><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z" /></Line>;
export const TrashIcon = (p: P) => <Line size={17} {...p}><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" /></Line>;
export const BoltIcon = (p: P) => <Line {...p}><path d="M13 2 4 14h7l-1 8 9-12h-7z" /></Line>;
export const ClockIcon = (p: P) => <Line {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></Line>;
export const CalendarIcon = (p: P) => <Line {...p}><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M8 3v4M16 3v4M3 10h18" /></Line>;
export const WalletIcon = (p: P) => <Line {...p}><rect x="3" y="6" width="18" height="14" rx="3" /><path d="M3 10h18M16 15h2" /></Line>;
export const UploadIcon = (p: P) => <Line {...p}><path d="M7 18a5 5 0 01-.6-9.96A6 6 0 0118 9a4 4 0 010 9M12 12v8M9 15l3-3 3 3" /></Line>;
export const ShieldIcon = (p: P) => <Line {...p}><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" /><path d="M9 12l2 2 4-4" /></Line>;
export const InfoIcon = (p: P) => <Line size={16} {...p}><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8v.01" /></Line>;
export const PinIcon = (p: P) => <Line {...p}><path d="M12 22s7-6.5 7-12a7 7 0 10-14 0c0 5.5 7 12 7 12z" /><circle cx="12" cy="10" r="2.5" /></Line>;
export const OccupantsIcon = (p: P) => <Line {...p}><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20c0-3.6 3-6 6.5-6s6.5 2.4 6.5 6M17 5a3.2 3.2 0 010 6.2M19 14.5c1.6.8 2.5 2.6 2.5 5.5" /></Line>;
export const HomeTypeIcon = (p: P) => <Line {...p}><path d="M3 11 12 4l9 7M5 10v10h14V10M10 20v-6h4v6" /></Line>;
export const FileIcon = (p: P) => <Line {...p}><path d="M6 3h8l5 5v13H6zM14 3v5h5M9 13h6M9 17h6" /></Line>;
export const SearchIcon = (p: P) => <Line {...p}><circle cx="11" cy="11" r="7" /><path d="M20 20l-4-4" /></Line>;
export const UserIcon = (p: P) => <Line {...p}><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 3.5-6 8-6s8 2 8 6" /></Line>;
export const HelpIcon = (p: P) => <Line {...p}><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 015 .5c0 1.5-2.5 2-2.5 3.5M12 17v.01" /></Line>;
export const CloseIcon = (p: P) => <Line {...p}><path d="M6 6l12 12M18 6 6 18" /></Line>;
