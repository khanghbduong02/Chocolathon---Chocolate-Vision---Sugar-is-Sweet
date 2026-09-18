import { useEffect, useRef, useState } from "react";
import { useAssemblyAiMic } from "./hooks/useAssemblyAiMic";
import { useBoxPacking } from "./hooks/useBoxPacking";
import { BOX_SIZE_OPTIONS } from "./constants/config";

import Header from "./components/Header";
import BoxSizeSelector from "./components/BoxSizeSelector";
import StatusBanner from "./components/StatusBanner";
import CameraPanel from "./components/CameraPanel";
import VoicePanel from "./components/VoicePanel";
import OrderLogCard from "./components/OrderLogCard";
import BoxControls from "./components/BoxControls";
import InsightsPanel from "./components/InsightsPanel";
import ReviewPanel from "./components/ReviewPanel";

export default function CocoaVision() {
  const [boxSize, setBoxSize] = useState(BOX_SIZE_OPTIONS[0]);
  const [showInsights, setShowInsights] = useState(false);
  const [flavorCatalog, setFlavorCatalog] = useState([]);
  const [cameraReady, setCameraReady] = useState(false);
  const handleMatchesRef = useRef(() => {});
  const cameraRef = useRef(null);

  const {
    micOn,
    micError,
    liveTranscript,
    setLiveTranscript,
    startMic,
    stopMic,
  } = useAssemblyAiMic((matches) => handleMatchesRef.current(matches), flavorCatalog);

  useEffect(() => {
    fetch("/api/flavors").then((response) => response.ok ? response.json() : Promise.reject(new Error())).then((data) => setFlavorCatalog(data.flavors || [])).catch(() => {});
  }, []);

  const packing = useBoxPacking({
    startMic,
    stopMic,
    setLiveTranscript,
    boxSize,
  });

  useEffect(() => {
    handleMatchesRef.current = (matches) => {
      packing.addVoiceMatches(matches);
    };
  });

  return (
    <div className="app-shell">
      <Header micOn={micOn} cameraReady={cameraReady} elapsed={packing.elapsed} phase={packing.phase} />

      <BoxSizeSelector
        boxSize={boxSize}
        setBoxSize={setBoxSize}
        locked={packing.itemsEditable}
      />

      <StatusBanner
        phase={packing.phase}
        boxLocked={packing.boxLocked}
        remaining={packing.remaining}
        voicePieces={packing.voicePieces}
        scalePieces={packing.scalePieces}
        elapsed={packing.elapsed}
      />

      {micError && (
        <div className="inline-error page-error">
          Microphone: {micError}
        </div>
      )}

      <main className="main-content">
        <div className="work-grid">
            <CameraPanel ref={cameraRef} phase={packing.phase} micOn={micOn} onCameraReady={setCameraReady} boxLocked={packing.boxLocked} capturedImage={packing.capturedImage} annotatedImage={packing.annotatedImage} />
            <VoicePanel
              phase={packing.phase}
              boxLocked={packing.boxLocked}
              voiceItems={packing.voiceItems}
              liveTranscript={liveTranscript}
              voicePieces={packing.voicePieces}
              voiceStatus={packing.voiceStatus}
              boxSize={boxSize}
            />
        </div>

        {packing.phase === "review" && <ReviewPanel comparison={packing.comparison} items={packing.voiceItems} itemsEditable={packing.itemsEditable} onAdjustQty={packing.adjustItemQty} onRemoveItem={packing.removeItem} onSave={packing.saveOrder} saving={packing.saving} saveError={packing.saveError} />}

        {packing.saveError && packing.phase !== "review" && <div className="inline-error page-error">{packing.saveError}</div>}

        <OrderLogCard
          orderLog={packing.orderLog}
          flavors={flavorCatalog}
          onUpdateOrder={packing.updateOrder}
          onDeleteOrder={packing.deleteOrder}
          onDownload={packing.downloadOrderLog}
          onClearLog={packing.clearOrderLog}
          onOpenInsights={() => setShowInsights(true)}
        />
      </main>

      <BoxControls
        phase={packing.phase}
        boxLocked={packing.boxLocked}
        onBeginBox={packing.beginBox}
        onReset={packing.resetToIdle}
        onFinish={() => packing.finishRecordingAndScan(() => cameraRef.current.capture())}
      />

      {showInsights && (
        <InsightsPanel
          orderLog={packing.orderLog}
          onClose={() => setShowInsights(false)}
        />
      )}
    </div>
  );
}
