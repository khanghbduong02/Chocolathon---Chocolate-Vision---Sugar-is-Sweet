import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";

function waitForVideoFrame(video) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + 2500;
    const check = () => {
      if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && video.videoWidth > 0) {
        resolve();
        return;
      }
      if (Date.now() >= deadline) {
        reject(new Error("Camera did not produce a video frame."));
        return;
      }
      requestAnimationFrame(check);
    };
    check();
  });
}

function hasUsableLight(video) {
  const canvas = document.createElement("canvas");
  canvas.width = 64;
  canvas.height = 36;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
  let total = 0;
  let brightPixels = 0;
  for (let index = 0; index < pixels.length; index += 4) {
    const luminance = pixels[index] * 0.2126 + pixels[index + 1] * 0.7152 + pixels[index + 2] * 0.0722;
    total += luminance;
    if (luminance > 24) brightPixels += 1;
  }
  const mean = total / (pixels.length / 4);
  return mean > 10 && brightPixels > pixels.length / 4 / 12;
}

const CameraPanel = forwardRef(function CameraPanel({ phase, micOn, boxLocked, capturedImage, annotatedImage, onCameraReady }, ref) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [cameraError, setCameraError] = useState("");
  const [cameraReady, setCameraReady] = useState(false);
  const [facingMode, setFacingMode] = useState("environment");
  const [showClassifications, setShowClassifications] = useState(true);

  const startCamera = useCallback(async (requestedFacingMode = facingMode) => {
    setCameraError("");
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError("This browser does not provide camera access.");
      return;
    }

    const deviceConstraints = [{
      video: { facingMode: { ideal: requestedFacingMode }, width: { ideal: 1920 }, height: { ideal: 1080 } },
      audio: false,
    }];
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      devices.filter((device) => device.kind === "videoinput" && device.deviceId).forEach((device) => {
        deviceConstraints.push({ video: { deviceId: { exact: device.deviceId }, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false });
      });
    } catch {
      // The preferred facing-mode request below can still succeed if enumeration is restricted.
    }

    let lastError = null;
    for (const constraints of deviceConstraints) {
      try {
        streamRef.current?.getTracks().forEach((track) => track.stop());
        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        streamRef.current = stream;
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        await waitForVideoFrame(videoRef.current);
        if (!hasUsableLight(videoRef.current)) throw new Error("Camera produced a blank or dark frame.");
        setCameraReady(true);
        onCameraReady?.(true);
        return;
      } catch (error) {
        lastError = error;
        streamRef.current?.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
    }

    setCameraReady(false);
    onCameraReady?.(false);
    setCameraError(lastError?.message || "No available camera produced a usable image.");
  }, [facingMode, onCameraReady]);

  useEffect(() => {
    if (phase === "listening" && micOn && !cameraReady) {
      startCamera();
    }
    if (phase === "idle" || phase === "saved" || phase === "review") {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setCameraReady(false);
      onCameraReady?.(false);
    }
  }, [cameraReady, micOn, onCameraReady, phase, startCamera]);

  useEffect(() => () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    onCameraReady?.(false);
  }, [onCameraReady]);

  const switchCamera = useCallback(async () => {
    const nextFacingMode = facingMode === "environment" ? "user" : "environment";
    setFacingMode(nextFacingMode);
    setCameraReady(false);
    await startCamera(nextFacingMode);
  }, [facingMode, startCamera]);

  useImperativeHandle(ref, () => ({
    capture: async () => {
      if (!videoRef.current || !cameraReady) throw new Error("Camera is not ready.");
      const canvas = document.createElement("canvas");
      canvas.width = videoRef.current.videoWidth;
      canvas.height = videoRef.current.videoHeight;
      canvas.getContext("2d").drawImage(videoRef.current, 0, 0);
      return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
    },
    start: startCamera,
    stop: () => {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setCameraReady(false);
      onCameraReady?.(false);
    },
    switchCamera,
  }), [cameraReady, onCameraReady, startCamera, switchCamera]);

  return (
    <section className="camera-panel">
      <div className="panel-heading">
        <div><span className="eyebrow">Visual evidence</span><h2>Live camera</h2></div>
        <span className={`camera-status ${cameraReady ? "ready" : ""}`}>{cameraReady ? "Ready" : "Offline"}</span>
      </div>
      <div className="camera-frame">
        {phase === "review" && capturedImage ? (
          showClassifications && annotatedImage ? (
            <img className="captured-frame" src={`data:image/jpeg;base64,${annotatedImage}`} alt="Captured box with classified items" />
          ) : (
            <img className="captured-frame" src={capturedImage} alt="Captured chocolate box" />
          )
        ) : <video ref={videoRef} playsInline muted aria-label="Live box camera" />}
        {!cameraReady && phase !== "review" && phase !== "scanning" && (
          <div className="camera-placeholder">
            <span className="camera-glyph">◉</span>
            {phase === "listening" && micOn ? (
              <>
                <p>Position the open box in frame.</p>
                <button className="button secondary" onClick={startCamera}>Enable camera</button>
              </>
            ) : (
              <p>Click Start New Box to begin.</p>
            )}
          </div>
        )}
        {phase === "scanning" && <div className="camera-scan-overlay">Scanning box...</div>}
      </div>
      {cameraError && <p className="inline-error">{cameraError}</p>}
      <div className="camera-actions">
        {phase === "review" && capturedImage && annotatedImage && <button className="button secondary" onClick={() => setShowClassifications((visible) => !visible)}>{showClassifications ? "Hide classifications" : "Show classifications"}</button>}
        {cameraReady && phase === "listening" && <button className="button secondary" onClick={switchCamera}>Switch camera</button>}
      </div>
      <p className="panel-hint">The captured frame is saved with the order as original evidence.</p>
      {boxLocked && <p className="panel-hint">This box is saved. Start a new box to capture again.</p>}
    </section>
  );
});

export default CameraPanel;