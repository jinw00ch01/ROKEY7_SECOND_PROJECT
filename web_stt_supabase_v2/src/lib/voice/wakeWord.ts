// Browser wake-word using the Web Speech API. The Python flow uses an
// openwakeword TFLite model ("hello_rokey"); porting that requires three
// extra TFLite models (mel-spectrogram, embedding, keyword) plus a JS
// inference runtime. Until that lands, we listen for the keyword phrase
// via continuous SpeechRecognition.
//
// Runs in Chrome/Edge (webkitSpeechRecognition). Firefox/Safari fall back
// to a noop that resolves only on manual cancel.

type SpeechRecognitionResult = {
  isFinal: boolean;
  0: { transcript: string };
};

type SpeechRecognitionEvent = {
  resultIndex: number;
  results: { length: number; [index: number]: SpeechRecognitionResult };
};

type SpeechRecognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

type SpeechRecognitionCtor = new () => SpeechRecognition;

const DEFAULT_KEYWORDS = [
  "hello rokey",
  "헬로 로키",
  "헬로로키",
  "샤갈",
  "헤이 로키",
  "hey rokey",
];

function getRecognitionCtor(): SpeechRecognitionCtor | null {
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function isWakeWordSupported(): boolean {
  return getRecognitionCtor() !== null;
}

export type WakeWordController = {
  promise: Promise<boolean>;
  cancel: () => void;
};

function transcriptHits(transcript: string, keywords: string[]): boolean {
  const sample = transcript.toLowerCase();
  return keywords.some((kw) => sample.includes(kw.toLowerCase()));
}

export function listenForWakeWord(
  keywords: string[] = DEFAULT_KEYWORDS,
  language = "ko-KR",
): WakeWordController {
  const Ctor = getRecognitionCtor();

  if (!Ctor) {
    let cancel = () => {};
    const promise = new Promise<boolean>((resolve) => {
      cancel = () => resolve(false);
    });
    return { promise, cancel };
  }

  const recognition = new Ctor();
  recognition.lang = language;
  recognition.continuous = true;
  recognition.interimResults = true;

  let cancelled = false;
  let resolved = false;

  let resolveResult: (value: boolean) => void = () => {};
  const promise = new Promise<boolean>((resolve) => {
    resolveResult = resolve;
  });

  const finish = (value: boolean) => {
    if (resolved) return;
    resolved = true;
    try {
      recognition.stop();
    } catch {
      /* noop */
    }
    resolveResult(value);
  };

  recognition.onresult = (event) => {
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0]?.transcript ?? "";
      if (transcriptHits(transcript, keywords)) {
        finish(true);
        return;
      }
    }
  };

  recognition.onerror = (event) => {
    if (event.error === "no-speech" || event.error === "audio-capture") return;
    if (cancelled) return;
    finish(false);
  };

  recognition.onend = () => {
    if (resolved || cancelled) return;
    try {
      recognition.start();
    } catch {
      finish(false);
    }
  };

  try {
    recognition.start();
  } catch (error) {
    console.warn("Wake-word recognition failed to start:", error);
    finish(false);
  }

  return {
    promise,
    cancel: () => {
      cancelled = true;
      try {
        recognition.abort();
      } catch {
        /* noop */
      }
      finish(false);
    },
  };
}
