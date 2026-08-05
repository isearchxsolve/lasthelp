import React, { useEffect, useRef, useState, useCallback } from "react";
import "../styles/avatar-renderer.css";

interface AvatarRendererProps {
  webrtcUrl?: string;
  sessionId?: string;
  iceServers?: RTCIceServer[];
  onConnectionStateChange?: (state: "connecting" | "connected" | "disconnected" | "failed") => void;
  isSpeaking?: boolean;
  isListening?: boolean;
  expression?: string;
}

/**
 * AvatarRenderer — Real-time WebRTC video stream for HeyGen/D-ID avatars.
 * Renders the AI avatar with smooth state transitions and visual feedback.
 */
export const AvatarRenderer: React.FC<AvatarRendererProps> = ({
  webrtcUrl,
  sessionId,
  iceServers = [{ urls: "stun:stun.l.google.com:19302" }],
  onConnectionStateChange,
  isSpeaking = false,
  isListening = false,
  expression = "neutral",
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const [connectionState, setConnectionState] = useState<"connecting" | "connected" | "disconnected" | "failed">("connecting");
  const [hasVideo, setHasVideo] = useState(false);

  // Initialize WebRTC connection
  useEffect(() => {
    if (!webrtcUrl || !sessionId) return;

    const pc = new RTCPeerConnection({ iceServers });
    pcRef.current = pc;

    pc.onconnectionstatechange = () => {
      const state = pc.connectionState as any;
      setConnectionState(state);
      onConnectionStateChange?.(state);
    };

    pc.ontrack = (event) => {
      if (event.track.kind === "video" && videoRef.current) {
        videoRef.current.srcObject = event.streams[0];
        setHasVideo(true);
      }
    };

    // Fetch SDP offer from HeyGen and set remote description
    const connect = async () => {
      try {
        // In production, this would be the actual HeyGen SDP offer
        // For now, we simulate the connection flow
        const resp = await fetch(webrtcUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, action: "connect" }),
        });
        if (!resp.ok) throw new Error(`Failed to connect: ${resp.status}`);

        const data = await resp.json();
        const sdpOffer = data.sdp_offer;

        if (sdpOffer) {
          await pc.setRemoteDescription(new RTCSessionDescription(sdpOffer));
          const answer = await pc.createAnswer();
          await pc.setLocalDescription(answer);

          // Send answer back
          await fetch(webrtcUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              session_id: sessionId,
              action: "answer",
              sdp: answer.sdp,
            }),
          });
        }
      } catch (err) {
        console.error("WebRTC connection failed:", err);
        setConnectionState("failed");
      }
    };

    connect();

    return () => {
      pc.close();
      pcRef.current = null;
      setHasVideo(false);
    };
  }, [webrtcUrl, sessionId, iceServers, onConnectionStateChange]);

  // Visual feedback for speaking/listening states
  const getAvatarClass = useCallback(() => {
    const classes = ["avatar-video"];
    if (isSpeaking) classes.push("avatar-speaking");
    if (isListening) classes.push("avatar-listening");
    if (expression) classes.push(`avatar-expression-${expression}`);
    return classes.join(" ");
  }, [isSpeaking, isListening, expression]);

  return (
    <div className="avatar-renderer-container">
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted={false} // Avatar audio comes through here
        className={getAvatarClass()}
      />

      {!hasVideo && (
        <div className="avatar-placeholder">
          <div className="avatar-silhouette">
            <div className="avatar-head" />
            <div className="avatar-shoulders" />
          </div>
          <div className="avatar-status">
            {connectionState === "connecting" && (
              <>
                <div className="avatar-spinner" />
                <span>Connecting to avatar...</span>
              </>
            )}
            {connectionState === "failed" && (
              <span className="avatar-error">Avatar connection failed</span>
            )}
          </div>
        </div>
      )}

      {/* Visual indicators for speaking/listening */}
      <div className="avatar-indicators">
        {isSpeaking && (
          <div className="indicator speaking-indicator">
            <div className="wave-bar" />
            <div className="wave-bar" />
            <div className="wave-bar" />
            <span>Speaking</span>
          </div>
        )}
        {isListening && !isSpeaking && (
          <div className="indicator listening-indicator">
            <div className="pulse-ring" />
            <span>Listening</span>
          </div>
        )}
      </div>

      {/* Expression badge */}
      {expression && expression !== "neutral" && (
        <div className={`expression-badge expression-${expression}`}>
          {expression}
        </div>
      )}
    </div>
  );
};

export default AvatarRenderer;
