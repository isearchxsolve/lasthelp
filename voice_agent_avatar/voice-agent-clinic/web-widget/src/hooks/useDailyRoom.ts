import { useEffect, useState } from "react";

interface UseDailyRoomReturn {
  roomUrl: string | null;
  token: string | null;
  isLoading: boolean;
  error: string | null;
}

export function useDailyRoom(agentName: string = "clinic-agent"): UseDailyRoomReturn {
  const [roomUrl, setRoomUrl] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchRoom = async () => {
      try {
        const apiUrl = import.meta.env.VITE_DAILY_API_URL || "/api/daily-token";
        const resp = await fetch(`${apiUrl}?agent=${encodeURIComponent(agentName)}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        });
        if (!resp.ok) {
          throw new Error(`Failed to get room: ${resp.status} ${resp.statusText}`);
        }
        const data = await resp.json();
        setRoomUrl(data.roomUrl || data.url || null);
        setToken(data.token || null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setIsLoading(false);
      }
    };

    fetchRoom();
  }, [agentName]);

  return { roomUrl, token, isLoading, error };
}

export default useDailyRoom;
