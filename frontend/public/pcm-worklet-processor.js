// Runs on the audio rendering thread. Collects the small fixed-size blocks
// the Web Audio API hands out (128 frames at a time) into 4096-sample
// chunks — matching the old ScriptProcessorNode's buffer size — then posts
// each chunk to the main thread.
class PCMCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._chunks = [];
    this._bufferedLength = 0;
    this._chunkSize = 4096;
  }

  process(inputs) {
    const input = inputs[0];
    const channel = input && input[0];
    if (channel) {
      this._chunks.push(channel.slice()); // copy — the original buffer gets reused
      this._bufferedLength += channel.length;

      if (this._bufferedLength >= this._chunkSize) {
        const merged = new Float32Array(this._bufferedLength);
        let offset = 0;
        for (const chunk of this._chunks) {
          merged.set(chunk, offset);
          offset += chunk.length;
        }
        this.port.postMessage(merged, [merged.buffer]); // transfer, not copy
        this._chunks = [];
        this._bufferedLength = 0;
      }
    }
    return true;
  }
}

registerProcessor("pcm-capture-processor", PCMCaptureProcessor);