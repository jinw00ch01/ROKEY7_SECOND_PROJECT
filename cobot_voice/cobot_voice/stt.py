from openai import OpenAI
import sounddevice as sd
import scipy.io.wavfile as wav
import tempfile


class STT:
    def __init__(self, openai_api_key):
        self.client = OpenAI(api_key=openai_api_key)
        self.duration = 5  # seconds
        self.samplerate = 16000  # Whisper prefers 16kHz

    def speech2text(self, status_callback=None):
        print("음성 녹음을 시작합니다. \n 5초 동안 말해주세요...")
        if status_callback:
            status_callback("listening")
        audio = sd.rec(
            int(self.duration * self.samplerate),
            samplerate=self.samplerate,
            channels=1,
            dtype='int16',
        )
        sd.wait()
        print("녹음 완료. Whisper에 전송 중...")
        if status_callback:
            status_callback("transcribing")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            wav.write(temp_wav.name, self.samplerate, audio)

            with open(temp_wav.name, "rb") as f:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1", file=f
                )

        print("STT 결과: ", transcript.text)
        return transcript.text
