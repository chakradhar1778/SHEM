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

  /** The most recent bill record, or null if bill history is empty */
  latestBill: BillRecord | null;

  /** Adds a new bill record with validation and persistence; `file` (image/PDF) is stored after the bill is saved */
  addBill: (input: BillInput, file?: File | null) => BillRecord | null;

  /** Store (or replace) a bill's document so it can be viewed later. Resolves with an error message or null. */
  attachDocument: (id: string, file: File) => Promise<string | null>;

  /** Remove a bill's stored document */
  removeDocument: (id: string) => Promise<string | null>;

  /** Updates an existing bill record by ID with validation and persistence */
  updateBill: (id: string, input: Partial<BillInput>) => BillRecord | null;

  /** Deletes a bill record by ID with persistence */
  deleteBill: (id: string) => boolean;

  /** Currently selected location/category filter for bills */
  selectedLocation: string;

  /** Sets the active location filter */
  setSelectedLocation: (location: string) => void;
}

export const BillContext = createContext<BillContextType | null>(null);
