"use client";

import React, { useEffect, useRef, useState } from "react";
import { Mic, Square, Upload, AlertCircle, CheckCircle2, Trash2 } from "lucide-react";
import { apiFetch } from "../../lib/constants";
import { VoiceNoteRecord } from "../../types";

interface VoiceRecorderWidgetProps {
  missionId: string;
  linkedEventType?: "SOS" | "OBSERVATION";
  onUploaded: (voiceNote: VoiceNoteRecord) => void;
  compact?: boolean;
}

export function VoiceRecorderWidget({
  missionId,
  linkedEventType,
  onUploaded,
  compact = false,
}: VoiceRecorderWidgetProps) {
  const [recording, setRecording] = useState(false);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadedRecord, setUploadedRecord] = useState<VoiceNoteRecord | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop());
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  const startRecording = async () => {
    setErrorMsg(null);
    setUploadedRecord(null);
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setErrorMsg("Browser audio capture (MediaRecorder) is unavailable. Text SOS and text reports remain fully operational.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      const preferredMime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "";
      const recorder = preferredMime ? new MediaRecorder(stream, { mimeType: preferredMime }) : new MediaRecorder(stream);
      recorderRef.current = recorder;

      recorder.ondataavailable = (ev) => {
        if (ev.data && ev.data.size > 0) chunksRef.current.push(ev.data);
      };
      recorder.onstop = () => {
        const mime = recorder.mimeType || "audio/webm";
        const blob = new Blob(chunksRef.current, { type: mime });
        if (audioUrl) URL.revokeObjectURL(audioUrl);
        setAudioBlob(blob);
        setAudioUrl(URL.createObjectURL(blob));
        stream.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      };

      recorder.start(250);
      setRecording(true);
      setElapsedSec(0);
      timerRef.current = setInterval(() => setElapsedSec((s) => s + 1), 1000);
    } catch (err) {
      setErrorMsg(
        err instanceof Error
          ? `Microphone permission denied or unavailable: ${err.message}. You can continue without audio.`
          : "Microphone access denied. Continue with text report."
      );
    }
  };

  const stopRecording = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    recorderRef.current?.stop();
    setRecording(false);
  };

  const uploadBlob = async () => {
    if (!audioBlob || !missionId) return;
    setUploading(true);
    setErrorMsg(null);
    try {
      const q = new URLSearchParams();
      if (elapsedSec > 0) q.set("duration_seconds", String(elapsedSec));
      if (linkedEventType) q.set("linked_event_type", linkedEventType);
      const res = await apiFetch(`/missions/${missionId}/voice-notes?${q.toString()}`, {
        method: "POST",
        headers: {
          "Content-Type": audioBlob.type || "audio/webm",
        },
        body: audioBlob,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Audio upload failed." }));
        setErrorMsg(err.detail || "Audio upload failed.");
        return;
      }
      const saved: VoiceNoteRecord = await res.json();
      setUploadedRecord(saved);
      onUploaded(saved);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Network error while uploading audio.");
    } finally {
      setUploading(false);
    }
  };

  const resetAudio = () => {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    setAudioBlob(null);
    setAudioUrl(null);
    setUploadedRecord(null);
    setElapsedSec(0);
    setErrorMsg(null);
  };

  return (
    <div className={`rounded-[6px] border border-[var(--border-strong)] bg-[var(--bg-void)] ${compact ? "p-2.5" : "p-3"} space-y-2`}>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          {!recording ? (
            <button
              type="button"
              onClick={startRecording}
              disabled={!missionId || uploading}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-[4px] bg-[var(--bg-elevated)] hover:bg-white/10 border border-[var(--border-strong)] text-xs font-medium text-[var(--text-primary)] disabled:opacity-40"
            >
              <Mic className="w-3.5 h-3.5 text-[var(--accent-mars)]" />
              <span>{audioBlob ? "Re-record Voice Note" : "Record Voice Note"}</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={stopRecording}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-[4px] bg-[#DC3545] hover:bg-[#DC3545]/90 text-xs font-semibold text-white"
            >
              <Square className="w-3.5 h-3.5" />
              <span>Stop ({elapsedSec}s)</span>
            </button>
          )}
          {audioBlob && !recording && !uploadedRecord && (
            <button
              type="button"
              onClick={uploadBlob}
              disabled={uploading}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-[4px] bg-[var(--accent-telemetry)] text-[#07090C] text-xs font-semibold hover:opacity-90 disabled:opacity-50"
            >
              <Upload className="w-3.5 h-3.5" />
              <span>{uploading ? "Uploading..." : "Attach Audio"}</span>
            </button>
          )}
          {(audioBlob || uploadedRecord) && !recording && (
            <button
              type="button"
              onClick={resetAudio}
              aria-label="Clear recorded voice note"
              className="p-1.5 rounded-[4px] text-[var(--text-muted)] hover:text-[#ff6b7a]"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
        <span className="text-[11px] font-mono text-[var(--text-muted)]">
          {recording ? "CAPTURING AUDIO..." : uploadedRecord ? "UPLOADED & HASHED" : audioBlob ? `${elapsedSec}s ready` : "Optional audio"}
        </span>
      </div>

      {audioUrl && <audio controls src={audioUrl} className="w-full h-8" />}

      {uploadedRecord && (
        <div className="flex items-center gap-1.5 text-[11px] font-mono text-[#4ade80]">
          <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
          <span className="truncate">
            Attached ({Math.round(uploadedRecord.file_size_bytes / 1024)} KB, SHA-256 verified)
          </span>
        </div>
      )}

      {errorMsg && (
        <div className="flex items-start gap-1.5 text-[11px] text-[#f5b041]">
          <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          <span>{errorMsg}</span>
        </div>
      )}
    </div>
  );
}
