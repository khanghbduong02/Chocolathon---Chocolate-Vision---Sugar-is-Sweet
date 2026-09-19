import { useCallback, useEffect, useRef, useState } from "react";
import { floatTo16BitPCM } from "../utils/audio";
import { parseTranscript } from "../utils/transcript";
import {
  ASSEMBLYAI_WS_ENDPOINT,
  AUDIO_SAMPLE_RATE,
  TOKEN_ENDPOINT,
  apiFetch,
} from "../constants/config";

export function useAssemblyAiMic(onMatches, flavorCatalog) {
  const [micOn, setMicOn] = useState(false);
  const [micError, setMicError] = useState(null);
  const [liveTranscript, setLiveTranscript] = useState("");

  const socketRef = useRef(null);
  const audioCtxRef = useRef(null);
  const processorRef = useRef(null); // now holds the AudioWorkletNode
  const silentGainRef = useRef(null); // routes worklet output to destination without audible playback
  const streamRef = useRef(null);
  const onMatchesRef = useRef(onMatches);

  useEffect(() => {
    onMatchesRef.current = onMatches;
  }, [onMatches]);

  const stopMic = useCallback(() => {
    try {
      socketRef.current?.send(JSON.stringify({ type: "Terminate" }));
      socketRef.current?.close();
    } catch {
      /* socket may already be closed */
    }
    socketRef.current = null;

    if (processorRef.current) {
      processorRef.current.port.onmessage = null;
      processorRef.current.disconnect();
    }
    processorRef.current = null;

    silentGainRef.current?.disconnect();
    silentGainRef.current = null;

    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;

    if (audioCtxRef.current && audioCtxRef.current.state !== "closed") {
      audioCtxRef.current.close();
    }
    audioCtxRef.current = null;

    setMicOn(false);
  }, []);

  const startMic = useCallback(async () => {
    setMicError(null);
    try {
      const tokenRes = await apiFetch(TOKEN_ENDPOINT);
      if (!tokenRes.ok) throw new Error(`Token endpoint returned ${tokenRes.status}`);
      const { token } = await tokenRes.json();

      const socket = new WebSocket(
        `${ASSEMBLYAI_WS_ENDPOINT}?sample_rate=${AUDIO_SAMPLE_RATE}&token=${token}`
      );
      socketRef.current = socket;

      socket.onopen = async () => {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          streamRef.current = stream;

          const audioCtx = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: AUDIO_SAMPLE_RATE,
          });
          audioCtxRef.current = audioCtx;

          await audioCtx.audioWorklet.addModule("/pcm-worklet-processor.js");

          const source = audioCtx.createMediaStreamSource(stream);
          const workletNode = new AudioWorkletNode(audioCtx, "pcm-capture-processor");
          processorRef.current = workletNode;

          workletNode.port.onmessage = (event) => {
            if (socket.readyState !== WebSocket.OPEN) return;
            const pcm16 = floatTo16BitPCM(event.data);
            socket.send(pcm16.buffer);
          };

          // An AudioWorkletNode, like the old ScriptProcessorNode, only
          // keeps getting pulled by the audio graph if it's reachable from
          // the destination. Route through a zero-gain node so it stays
          // active without actually playing the mic back through speakers.
          const silentGain = audioCtx.createGain();
          silentGain.gain.value = 0;
          silentGainRef.current = silentGain;

          source.connect(workletNode);
          workletNode.connect(silentGain);
          silentGain.connect(audioCtx.destination);

          setMicOn(true);
        } catch (err) {
          setMicError(err.message || "Could not access the microphone.");
          setMicOn(false);
          socket.close();
        }
      };

      socket.onmessage = (msg) => {
        let data;
        try {
          data = JSON.parse(msg.data);
        } catch {
          return;
        }
        if (typeof data.transcript !== "string") return;

        setLiveTranscript(data.transcript);

        if (data.end_of_turn) {
          const matches = parseTranscript(data.transcript, flavorCatalog);
          if (matches.length > 0) {
            onMatchesRef.current?.(matches);
          }
          setLiveTranscript("");
        }
      };

      socket.onerror = () => {
        setMicError("Connection to AssemblyAI failed. Check your token endpoint and network.");
        stopMic();
      };

      socket.onclose = () => {
        setMicOn(false);
      };
    } catch (err) {
      setMicError(err.message || "Could not access the microphone.");
      setMicOn(false);
    }
  }, [flavorCatalog, stopMic]);

  useEffect(() => {
    return () => {
      stopMic();
    };
  }, [stopMic]);

  return { micOn, micError, liveTranscript, setLiveTranscript, startMic, stopMic };
}