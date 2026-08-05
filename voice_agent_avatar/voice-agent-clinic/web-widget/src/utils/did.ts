import { useState, useCallback, useRef, useEffect } from "react";

interface UseDIDStreamReturn {
  startSession: (avatarId?: string) => Promise<{ sessionId: string; webrtcUrl: string } | null>;
  stopSession: () => Promise<void>;
  sendSpeech: (text: string, voiceId?: string) => Promise<{ taskId: string; estimatedDuration: number } | null>;
  setExpression: (expression: string) => Promise<void>;
  isStreaming: boolean;
  isSpeaking: boolean;
  isListening: boolean;
  currentExpression: string;
  sessionId: string | null;
  webrtcUrl: string | null;
  error: string | null;
}

/**
 * useDIDStream — D-ID avatar streaming fallback hook.
 * Used when HeyGen is unavailable or fails to initialize.
 */
export function useDIDStream(): UseDIDStreamReturn {
  const [isStreaming, setIsStreaming] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [currentExpression, setCurrentExpression] = useState("neutral");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [webrtcUrl, setWebrtcUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const apiKey = import.meta.env.VITE_DID_API_KEY;
  const defaultAvatarId = import.meta.env.VITE_DID_AVATAR_ID;
  const baseUrl = "https://api.d-id.com";

  const speechTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const startSession = useCallback(async (avatarId?: string) => {
    if (isStreaming) return null;
    try {
      setError(null);
      const id = avatarId || defaultAvatarId;

      if (!apiKey || !id) {
        throw new Error("D-ID API key or avatar ID not configured");
      }

      // D-ID uses a different API pattern — create a talk stream
      const resp = await fetch(`${baseUrl}/talks/streams`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Basic ${apiKey}`,
        },
        body: JSON.stringify({
          source_url: id, // D-ID uses source_url instead of avatar_id
        }),
      });

      if (!resp.ok) throw new Error(`D-ID start failed: ${resp.status}`);
      const data = await resp.json();

      const sid = data.id;
      const wUrl = data.result_url; // D-ID WebRTC endpoint

      setSessionId(sid);
      setWebrtcUrl(wUrl || `${baseUrl}/talks/streams/${sid}/webrtc`);
      setIsStreaming(true);
      setIsListening(true);
      setCurrentExpression("listening");

      console.log("[D-ID] Session started:", sid);
      return { sessionId: sid, webrtcUrl: wUrl };
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setError(msg);
      console.error("[D-ID] Failed to start session:", err);
      return null;
    }
  }, [isStreaming, apiKey, defaultAvatarId]);

  const stopSession = useCallback(async () => {
    if (!isStreaming || !sessionId) return;
    try {
      await fetch(`${baseUrl}/talks/streams/${sessionId}`, {
        method: "DELETE",
        headers: {
          "Authorization": `Basic ${apiKey}`,
        },
      });
    } catch (err) {
      console.error("[D-ID] Stop error:", err);
    } finally {
      setIsStreaming(false);
      setIsSpeaking(false);
      setIsListening(false);
      setCurrentExpression("neutral");
      setSessionId(null);
      setWebrtcUrl(null);
      if (speechTimeoutRef.current) {
        clearTimeout(speechTimeoutRef.current);
        speechTimeoutRef.current = null;
      }
    }
  }, [isStreaming, sessionId, apiKey]);

  const sendSpeech = useCallback(async (text: string, voiceId?: string) => {
    if (!isStreaming || !sessionId) return null;
    try {
      setIsSpeaking(true);
      setIsListening(false);
      setCurrentExpression("speaking");

      const resp = await fetch(`${baseUrl}/talks/streams/${sessionId}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Basic ${apiKey}`,
        },
        body: JSON.stringify({
          script: {
            type: "text",
            input: text,
            provider: {
              type: "microsoft",
              voice_id: voiceId || "en-US-JennyNeural",
            },
          },
          config: {
            stitch: true,
          },
          session_id: sessionId,
        }),
      });

      if (!resp.ok) throw new Error(`Speech task failed: ${resp.status}`);
      const data = await resp.json();

      const estimatedDuration = data.duration || text.length * 80;

      if (speechTimeoutRef.current) clearTimeout(speechTimeoutRef.current);
      speechTimeoutRef.current = setTimeout(() => {
        setIsSpeaking(false);
        setIsListening(true);
        setCurrentExpression("listening");
      }, estimatedDuration + 200);

      return { taskId: data.id, estimatedDuration: estimatedDuration / 1000 };
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setError(msg);
      setIsSpeaking(false);
      setIsListening(true);
      console.error("[D-ID] Speech failed:", err);
      return null;
    }
  }, [isStreaming, sessionId, apiKey]);

  const setExpression = useCallback(async (expression: string) => {
    // D-ID doesn't support real-time expression changes like HeyGen
    // This is a no-op for D-ID, but we track the state for UI consistency
    setCurrentExpression(expression);
  }, []);

  useEffect(() => {
    return () => {
      if (speechTimeoutRef.current) {
        clearTimeout(speechTimeoutRef.current);
      }
      if (isStreaming && sessionId) {
        fetch(`${baseUrl}/talks/streams/${sessionId}`, {
          method: "DELETE",
          headers: { "Authorization": `Basic ${apiKey}` },
        }).catch(() => {});
      }
    };
  }, [isStreaming, sessionId, apiKey]);

  return {
    startSession,
    stopSession,
    sendSpeech,
    setExpression,
    isStreaming,
    isSpeaking,
    isListening,
    currentExpression,
    sessionId,
    webrtcUrl,
    error,
  };
}

export default useDIDStream;
