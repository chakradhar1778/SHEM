import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';

/** Shows a one-off message passed through navigation state: navigate(path, { state: { toast } }). */
export function RouteToast() {
  const location = useLocation();
  const incoming = (location.state as { toast?: string } | null)?.toast ?? null;
  const [message, setMessage] = useState<string | null>(incoming);

  useEffect(() => {
    if (!incoming) return;
    setMessage(incoming);
    const t = window.setTimeout(() => setMessage(null), 3500);
    return () => window.clearTimeout(t);
  }, [incoming, location.key]);

  if (!message) return null;
  return <div className="toast" role="status">{message}</div>;
}
