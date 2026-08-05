import { useState, useCallback, useRef, useEffect } from "react";

interface UseHeyGenStreamReturn {
  startSession: (avatarId?: string, voiceId?: string) => Promise<{ sessionId: string; webrtcUrl: string } | null>;
  stopSession: () => Promise<void>;
  sendSpeech: (text: string, expression?: string) => Promise<{ taskId: string; estimatedDuration: number } | null>;
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
 * useHeyGenStream — Real-time HeyGen avatar streaming hook.
 * Manages WebRTC session lifecycle, speech tasks, and expression state.
 */
export function useHeyGenStream(): UseHeyGenStreamReturn {
  const [isStreaming, setIsStreaming] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [currentExpression, setCurrentExpression] = useState("neutral");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [webrtcUrl, setWebrtcUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const apiKey = import.meta.env.VITE_HEYGEN_API_KEY;
  const defaultAvatarId = import.meta.env.VITE_HEYGEN_AVATAR_ID;
  const defaultVoiceId = import.meta.env.VITE_HEYGEN_VOICE_ID;
  const baseUrl = import.meta.env.VITE_HEYGEN_BASE_URL || "https://api.heygen.com/v1";

  const speechTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const startSession = useCallback(async (avatarId?: string, voiceId?: string) => {
    if (isStreaming) return null;
    try {
      setError(null);
      const id = avatarId || defaultAvatarId;
      const vId = voiceId || defaultVoiceId;

      if (!apiKey || !id) {
        throw new Error("HeyGen API key or avatar ID not configured");
      }

      const resp = await fetch(`${baseUrl}/streaming/start`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Api-Key": apiKey,
        },
        body: JSON.stringify({
          avatar_id: id,
          voice_id: vId,
          quality: "high",
          resolution: "720p",
          enable_lip_sync: true,
        }),
      });

      if (!resp.ok) throw new Error(`HeyGen start failed: ${resp.status}`);
      const data = await resp.json();

      const sid = data.session_id;
      const wUrl = data.webrtc_url;

      setSessionId(sid);
      setWebrtcUrl(wUrl);
      setIsStreaming(true);
      setIsListening(true);
      setCurrentExpression("listening");

      console.log("[HeyGen] Session started:", sid);
      return { sessionId: sid, webrtcUrl: wUrl };
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setError(msg);
      console.error("[HeyGen] Failed to start session:", err);
      return null;
    }
  }, [isStreaming, apiKey, defaultAvatarId, defaultVoiceId, baseUrl]);

  const stopSession = useCallback(async () => {
    if (!isStreaming || !sessionId) return;
    try {
      await fetch(`${baseUrl}/streaming/stop`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Api-Key": apiKey,
        },
        body: JSON.stringify({ session_id: sessionId }),
      });
    } catch (err) {
      console.error("[HeyGen] Stop error:", err);
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
  }, [isStreaming, sessionId, apiKey, baseUrl]);

  const sendSpeech = useCallback(async (text: string, expression?: string) => {
    if (!isStreaming || !sessionId) return null;
    try {
      setIsSpeaking(true);
      setIsListening(false);
      setCurrentExpression(expression || "speaking");

      const resp = await fetch(`${baseUrl}/streaming/task`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Api-Key": apiKey,
        },
        body: JSON.stringify({
          session_id: sessionId,
          text,
          voice_id: defaultVoiceId,
          expression: expression || "neutral",
          enable_lip_sync: true,
        }),
      });

      if (!resp.ok) throw new Error(`Speech task failed: ${resp.status}`);
      const data = await resp.json();

      const estimatedDuration = data.estimated_duration_ms || text.length * 80;

      // Auto-reset to listening after speech
      if (speechTimeoutRef.current) clearTimeout(speechTimeoutRef.current);
      speechTimeoutRef.current = setTimeout(() => {
        setIsSpeaking(false);
        setIsListening(true);
        setCurrentExpression("listening");
      }, estimatedDuration + 200);

      return { taskId: data.task_id, estimatedDuration: estimatedDuration / 1000 };
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setError(msg);
      setIsSpeaking(false);
      setIsListening(true);
      console.error("[HeyGen] Speech failed:", err);
      return null;
    }
  }, [isStreaming, sessionId, apiKey, baseUrl, defaultVoiceId]);

  const setExpression = useCallback(async (expression: string) => {
    if (!isStreaming || !sessionId) return;
    try {
      await fetch(`${baseUrl}/streaming/expression`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Api-Key": apiKey,
        },
        body: JSON.stringify({
          session_id: sessionId,
          expression,
          duration: 2.0,
        }),
      });
      setCurrentExpression(expression);
    } catch (err) {
      console.error("[HeyGen] Expression failed:", err);
    }
  }, [isStreaming, sessionId, apiKey, baseUrl]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (speechTimeoutRef.current) {
        clearTimeout(speechTimeoutRef.current);
      }
      if (isStreaming && sessionId) {
        fetch(`${baseUrl}/streaming/stop`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Api-Key": apiKey,
          },
          body: JSON.stringify({ session_id: sessionId }),
        }).catch(() => {});
      }
    };
  }, [isStreaming, sessionId, apiKey, baseUrl]);

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

export default useHeyGenStream;
