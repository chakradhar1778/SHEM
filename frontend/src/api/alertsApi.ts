import { apiRequest } from './backendApi';
import type { BudgetSaverSettings, NotificationItem, NotificationList } from './types';

export const fetchNotifications = (limit = 50) => apiRequest<NotificationList>(`/api/notifications?limit=${limit}`);

export const markNotificationRead = (id: number) =>
  apiRequest<NotificationItem>(`/api/notifications/${id}/read`, { method: 'POST' });

export const markAllNotificationsRead = () => apiRequest<NotificationList>('/api/notifications/read-all', { method: 'POST' });

/** Run the alert checks now (they also run on the backend every minute). */
export const checkNotifications = () => apiRequest<NotificationList>('/api/notifications/check', { method: 'POST' });

export const fetchBudgetSaver = () => apiRequest<BudgetSaverSettings>('/api/automation/budget-saver');

export const updateBudgetSaver = (patch: { mode?: BudgetSaverSettings['mode']; trigger?: BudgetSaverSettings['trigger'] }) =>
  apiRequest<BudgetSaverSettings>('/api/automation/budget-saver', { method: 'PUT', body: patch });
