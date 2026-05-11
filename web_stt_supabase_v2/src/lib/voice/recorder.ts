export type RecordedAudio = {
  blob: Blob;
  mimeType: string;
};

function pickMimeType(): string {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4",
  ];
  for (const candidate of candidates) {
    if (MediaRecorder.isTypeSupported(candidate)) return candidate;
  }
  return "";
}

export async function getMicrophoneStream(): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Microphone access is not supported in this browser.");
  }
  return navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
    },
  });
}

export async function recordAudio(
  durationMs: number,
  stream?: MediaStream,
): Promise<RecordedAudio> {
  const ownsStream = !stream;
  const activeStream = stream ?? (await getMicrophoneStream());
  const mimeType = pickMimeType();
  const recorder = mimeType
    ? new MediaRecorder(activeStream, { mimeType })
    : new MediaRecorder(activeStream);
  const chunks: BlobPart[] = [];

  return await new Promise<RecordedAudio>((resolve, reject) => {
    recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    });
    recorder.addEventListener("error", (event) => {
      reject((event as ErrorEvent).error ?? new Error("MediaRecorder error"));
    });
    recorder.addEventListener("stop", () => {
      if (ownsStream) {
        for (const track of activeStream.getTracks()) track.stop();
      }
      const finalType = recorder.mimeType || mimeType || "audio/webm";
      resolve({ blob: new Blob(chunks, { type: finalType }), mimeType: finalType });
    });

    recorder.start();
    setTimeout(() => {
      if (recorder.state !== "inactive") recorder.stop();
    }, durationMs);
  });
}
