import React, { useEffect, useRef, useState } from "react";
import { DailyProvider, useDaily } from "@daily-co/daily-react";
import { useHeyGenStream } from "../utils/heygen";
import "../styles/widget.css";

interface AvatarWidgetProps {
  roomUrl: string;
  token: string;
  avatarId?: string;
  onClose?: () => void;
  showBooking?: boolean;
}

const AvatarWidgetInner: React.FC<AvatarWidgetProps> = ({ roomUrl, token, onClose, showBooking = true }) => {
  const daily = useDaily();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [status, setStatus] = useState<"connecting" | "connected" | "disconnected" | "error">("connecting");
  const [showControls, setShowControls] = useState(true);

  const { startAvatar, stopAvatar, isStreaming } = useHeyGenStream();

  useEffect(() => {
    if (!daily) return;
    daily.join({ url: roomUrl, token }).catch((err) => {
      console.error("Join error:", err);
      setStatus("error");
    });

    daily.on("joined-meeting", () => setStatus("connected"));
    daily.on("left-meeting", () => setStatus("disconnected"));
    daily.on("error", () => setStatus("error"));

    return () => {
      daily.leave();
    };
  }, [daily, roomUrl, token]);

  useEffect(() => {
    if (!videoRef.current || !daily) return;

    // Get the remote AI participant's video track, not local camera
    const participants = Object.values(daily.participants() || {});
    const aiParticipant = participants.find((p) => p.local === false);
    if (aiParticipant) {
      const videoTrack = Object.values(aiParticipant.tracks || {}).find(
        (t: any) => t.kind === "video" && t.track
      );
      if (videoTrack && videoTrack.track) {
        videoRef.current.srcObject = new MediaStream([videoTrack.track]);
      }
    }
  }, [daily, status]);

  const handleMicToggle = () => {
    if (!daily) return;
    daily.setLocalAudio(!daily.localAudio());
  };

  const handleCameraToggle = () => {
    if (!daily) return;
    daily.setLocalVideo(!daily.localVideo());
  };

  const handleLeave = () => {
    if (!daily) return;
    daily.leave();
    stopAvatar();
    onClose?.();
  };

  const handleStartAvatar = async () => {
    await startAvatar();
  };

  const handleStopAvatar = () => {
    stopAvatar();
  };

  const toggleControls = () => {
    setShowControls((prev) => !prev);
  };

  return (
    <div className="avatar-widget-container">
      <div className="avatar-widget-header">
        <span className="avatar-widget-title">AI Assistant</span>
        <div className="avatar-widget-status">
          <span className={`status-dot status-${status}`} />
          {status}
        </div>
        <button className="avatar-widget-close" onClick={handleLeave} aria-label="Close">
          ×
        </button>
      </div>

      <div className="avatar-widget-video" onClick={toggleControls}>
        <video ref={videoRef} autoPlay playsInline muted className="avatar-video" />
        {status === "connecting" && (
          <div className="avatar-loading">
            <div className="spinner" />
            <p>Connecting to AI assistant...</p>
          </div>
        )}
      </div>

      {showControls && (
        <div className="avatar-widget-controls">
          <button onClick={handleMicToggle} className="control-btn" aria-label="Toggle microphone">
            🎤
          </button>
          <button onClick={handleCameraToggle} className="control-btn" aria-label="Toggle camera">
            📹
          </button>
          <button
            onClick={isStreaming ? handleStopAvatar : handleStartAvatar}
            className={`control-btn ${isStreaming ? "active" : ""}`}
            aria-label="Toggle avatar"
          >
            🤖
          </button>
          <button onClick={handleLeave} className="control-btn control-btn-end" aria-label="End call">
            📞
          </button>
        </div>
      )}

      {showBooking && status === "connected" && (
        <div className="avatar-widget-booking">
          <button className="booking-btn" onClick={() => alert("Booking integration coming soon!")}>
            📅 Book Appointment
          </button>
        </div>
      )}
    </div>
  );
};

export const AvatarWidget: React.FC<AvatarWidgetProps> = (props) => (
  <DailyProvider>
    <AvatarWidgetInner {...props} />
  </DailyProvider>
);

export default AvatarWidget;
