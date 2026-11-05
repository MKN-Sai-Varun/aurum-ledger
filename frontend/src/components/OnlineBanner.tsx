import { useEffect, useState } from "react";

export default function OnlineBanner() {
  const [online, setOnline] = useState(() => navigator.onLine);

  useEffect(() => {
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => {
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
    };
  }, []);

  if (online) return null;
  return (
    <p className="banner banner-page no-print" role="status">
      You are offline. What you type is kept on this device, and saving works again when the
      connection returns.
    </p>
  );
}