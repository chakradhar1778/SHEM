import { createContext } from 'react';
import type { SyncState } from './syncState';

/**
 * Represents a single user-entered electricity bill record.
 */
export interface BillRecord {
  /** Unique bill identifier, e.g. "bill_1711756800000_abc12" */
  id: string;

  /** Utility company / provider name, e.g. "BESCOM" */
  utilityProvider: string;

  /** Optional account ID / consumer number */
  accountId?: string;

  /** Billing calendar month (1-12) */
  billingMonth: number;

  /** Billing year (e.g. 2024) */
  billingYear: number;

  /** Human-readable billing period display label, e.g. "March 2024" */
  billingPeriod?: string;

  /** Optional billing period start date (ISO string YYYY-MM-DD) */
  billingPeriodStart?: string;

  /** Optional billing period end date (ISO string YYYY-MM-DD) */
  billingPeriodEnd?: string;

  /** Duration of billing cycle in days, defaults to 30 */
  billingPeriodDays?: number;

  /** Billed electricity consumption in kilowatt-hours (kWh) */
  unitsConsumed: number;

  /** Total billed amount in Indian Rupees (INR) */
  billAmount: number;

  /** Optional payment due date, e.g. "29 Oct" or "2024-04-15" */
  dueDate?: string;

  /** Bill location/category tag, e.g. "my_home" | "parents_home" | "office" */
  locationTag?: string;

  /** Optional filename of the uploaded bill document */
  documentFilename?: string;

  /** A document (image/PDF) is stored on the backend and can be viewed */
  hasDocument?: boolean;
  documentContentType?: string;
  documentSize?: number;
  /** Upload in progress or failed (UI state only) */
  documentStatus?: 'uploading' | 'failed';

  /** Local date (YYYY-MM-DD) the bill was paid; undefined = unpaid */
  paidOn?: string;

  /** Timestamp when this bill record was created */
  createdAt: number;
}

/**
 * Data payload for adding or updating a bill record.
 */
export interface BillInput {
  utilityProvider?: string;
  accountId?: string;
  billingMonth?: number;
  billingYear?: number;
  billingPeriod?: string;
  billingPeriodStart?: string;
  billingPeriodEnd?: string;
  billingPeriodDays?: number;
  unitsConsumed: number;
  billAmount: number;
  dueDate?: string;
  locationTag?: string;
  documentFilename?: string;
}

/**
 * Context interface for electricity bill state management.
 */
export interface BillContextType extends SyncState {
  /** Array of all saved bill records, sorted chronologically (newest first) */
  bills: BillRecord[];

  /** This home's bills (location "my_home"): the ones compared with SHEM's usage, tariff and budget */
  homeBills: BillRecord[];

  /** The most recent bill for THIS home (other locations never count), or null */
  latestBill: BillRecord | null;

  /** Adds a new bill record with validation and persistence; `file` (image/PDF) is stored after the bill is saved */
  addBill: (input: BillInput, file?: File | null) => BillRecord | null;

  /** Store (or replace) a bill's document so it can be viewed later. Resolves with an error message or null. */
  attachDocument: (id: string, file: File) => Promise<string | null>;

  /** Remove a bill's stored document */
  removeDocument: (id: string) => Promise<string | null>;

  /** Mark a bill paid (paidOn YYYY-MM-DD, default today) or unpaid (paid = false). Resolves with an error or null. */
  setPaid: (id: string, paid: boolean, paidOn?: string) => Promise<string | null>;

  /** Updates an existing bill record by ID with validation and persistence */
  updateBill: (id: string, input: Partial<BillInput>) => BillRecord | null;

  /** Deletes a bill record by ID with persistence */
  deleteBill: (id: string) => boolean;

  /** Currently selected location/category filter for bills */
  selectedLocation: string;

  /** Sets the active location filter */
  setSelectedLocation: (location: string) => void;
}

export const HOME_LOCATION = 'my_home';

export type BillPaymentTone = 'paid' | 'overdue' | 'due-soon' | 'due' | 'unpaid';

const dayDiff = (iso: string, today: Date) =>
  Math.round((new Date(`${iso}T12:00:00`).getTime() - new Date(today.getFullYear(), today.getMonth(), today.getDate(), 12).getTime()) / 86_400_000);

const short = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });

/** Payment status label for a bill (paid / overdue / due soon / due / unpaid). */
export function billPaymentStatus(b: Pick<BillRecord, 'paidOn' | 'dueDate'>, today = new Date()): { tone: BillPaymentTone; label: string } {
  if (b.paidOn) return { tone: 'paid', label: `Paid ${short(b.paidOn)}` };
  const due = b.dueDate && /^\d{4}-\d{2}-\d{2}$/.test(b.dueDate) ? b.dueDate : null;
  if (!due) return { tone: 'unpaid', label: 'Unpaid' };
  const d = dayDiff(due, today);
  if (d < 0) return { tone: 'overdue', label: `Overdue · was due ${short(due)}` };
  if (d === 0) return { tone: 'due-soon', label: 'Due today' };
  if (d <= 3) return { tone: 'due-soon', label: `Due in ${d} day${d === 1 ? '' : 's'}` };
  return { tone: 'due', label: `Due ${short(due)}` };
}

export const isHomeBill = (b: Pick<BillRecord, 'locationTag'>) => (b.locationTag || HOME_LOCATION) === HOME_LOCATION;

export const BillContext = createContext<BillContextType | null>(null);
