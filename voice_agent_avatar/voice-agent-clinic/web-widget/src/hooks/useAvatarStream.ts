import { useState, useCallback, useEffect, useRef } from "react";
import { useHeyGenStream } from "./heygen";
import { useDIDStream } from "./did";

interface UseAvatarStreamReturn {
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
  provider: "heygen" | "did" | null;
  error: string | null;
}

/**
 * useAvatarStream — Unified avatar streaming with automatic fallback.
 * Tries HeyGen first, falls back to D-ID if HeyGen fails.
 */
export function useAvatarStream(): UseAvatarStreamReturn {
  const [provider, setProvider] = useState<"heygen" | "did" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const heygen = useHeyGenStream();
  const did = useDIDStream();

  const activeProvider = provider === "heygen" ? heygen : provider === "did" ? did : null;

  const startSession = useCallback(async (avatarId?: string, voiceId?: string) => {
    setError(null);

    // Try HeyGen first
    if (import.meta.env.VITE_HEYGEN_API_KEY && import.meta.env.VITE_HEYGEN_AVATAR_ID) {
      console.log("[Avatar] Trying HeyGen...");
      const result = await heygen.startSession(avatarId, voiceId);
      if (result) {
        setProvider("heygen");
        return result;
      }
    }

    // Fallback to D-ID
    if (import.meta.env.VITE_DID_API_KEY && import.meta.env.VITE_DID_AVATAR_ID) {
      console.log("[Avatar] HeyGen failed, falling back to D-ID...");
      const result = await did.startSession(avatarId);
      if (result) {
        setProvider("did");
        return result;
      }
    }

    const err = "No avatar provider available. Check API keys and avatar IDs.";
    setError(err);
    console.error("[Avatar]", err);
    return null;
  }, [heygen, did]);

  const stopSession = useCallback(async () => {
    if (provider === "heygen") {
      await heygen.stopSession();
    } else if (provider === "did") {
      await did.stopSession();
    }
    setProvider(null);
  }, [provider, heygen, did]);

  const sendSpeech = useCallback(async (text: string, expression?: string) => {
    if (provider === "heygen") {
      return await heygen.sendSpeech(text, expression);
    } else if (provider === "did") {
      return await did.sendSpeech(text);
    }
    return null;
  }, [provider, heygen, did]);

  const setExpression = useCallback(async (expression: string) => {
    if (provider === "heygen") {
      await heygen.setExpression(expression);
    } else if (provider === "did") {
      await did.setExpression(expression);
    }
  }, [provider, heygen, did]);

  // Combine errors from both providers
  useEffect(() => {
    if (heygen.error) setError(`HeyGen: ${heygen.error}`);
    else if (did.error) setError(`D-ID: ${did.error}`);
    else setError(null);
  }, [heygen.error, did.error]);

  return {
    startSession,
    stopSession,
    sendSpeech,
    setExpression,
    isStreaming: activeProvider?.isStreaming || false,
    isSpeaking: activeProvider?.isSpeaking || false,
    isListening: activeProvider?.isListening || false,
    currentExpression: activeProvider?.currentExpression || "neutral",
    sessionId: activeProvider?.sessionId || null,
    webrtcUrl: activeProvider?.webrtcUrl || null,
    provider,
    error,
  };
}

export default useAvatarStream;