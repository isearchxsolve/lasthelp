import React, { useState } from "react";

interface CallControlsProps {
  onMuteToggle: () => void;
  isMuted: boolean;
  onVideoToggle: () => void;
  isVideoOn: boolean;
  onEndCall: () => void;
  onToggleAvatar: () => void;
  isAvatarOn: boolean;
}

export const CallControls: React.FC<CallControlsProps> = ({
  onMuteToggle,
  isMuted,
  onVideoToggle,
  isVideoOn,
  onEndCall,
  onToggleAvatar,
  isAvatarOn,
}) => {
  return (
    <div className="call-controls">
      <button
        onClick={onMuteToggle}
        className={`control-btn ${isMuted ? "muted" : ""}`}
        aria-label={isMuted ? "Unmute" : "Mute"}
        title={isMuted ? "Unmute" : "Mute"}
      >
        {isMuted ? "🔇" : "🎤"}
      </button>
      <button
        onClick={onVideoToggle}
        className={`control-btn ${!isVideoOn ? "video-off" : ""}`}
        aria-label={isVideoOn ? "Turn off camera" : "Turn on camera"}
        title={isVideoOn ? "Turn off camera" : "Turn on camera"}
      >
        {isVideoOn ? "📹" : "📷"}
      </button>
      <button
        onClick={onToggleAvatar}
        className={`control-btn ${isAvatarOn ? "active" : ""}`}
        aria-label={isAvatarOn ? "Hide avatar" : "Show avatar"}
        title={isAvatarOn ? "Hide avatar" : "Show avatar"}
      >
        🤖
      </button>
      <button
        onClick={onEndCall}
        className="control-btn end-call"
        aria-label="End call"
        title="End call"
      >
        📞
      </button>
    </div>
  );
};

export default CallControls;
