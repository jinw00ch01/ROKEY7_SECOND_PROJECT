# 한국어 요약:
#   PyAudio 기반 마이크 캡처 컨트롤러. wakeword/STT 파이프라인이 공유하는 입력
#   스트림 설정(48kHz / mono / int16)과 record_audio()를 제공한다.
#   device_index=6은 특정 호스트의 USB 마이크 번호로 하드코딩되어 있어 다른
#   환경에서는 동작하지 않을 수 있다(이식성 한계).
import pyaudio
import wave
import io
from dataclasses import dataclass, field


@dataclass
class MicConfig:
    chunk: int = 12000
    rate: int = 48000
    channels: int = 1
    record_seconds: int = 5
    fmt: int = field(default_factory=lambda: pyaudio.paInt16)
    # 호스트마다 다를 수 있는 입력 디바이스 번호. 다른 PC로 이식 시 재설정 필요.
    device_index: int = 6
    buffer_size: int = 24000


class MicController:
    def __init__(self, config: MicConfig = MicConfig()):
        self.config = config
        self.frames = []
        self.audio = None
        self.stream = None
        self.sample_width = None

    def open_stream(self):
        self.audio = pyaudio.PyAudio()
        self.sample_width = self.audio.get_sample_size(self.config.fmt)
        self.stream = self.audio.open(
            format=self.config.fmt,
            channels=self.config.channels,
            rate=self.config.rate,
            input=True,
            frames_per_buffer=self.config.chunk,
        )

    def close_stream(self):
        print("stop recording")
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.audio:
            self.audio.terminate()
            self.audio = None

    def record_audio(self) -> bytes:
        mic = MicController()
        mic.open_stream()

        print("start recording...")
        frames = []

        for _ in range(
            0, int(mic.config.rate / mic.config.chunk * mic.config.record_seconds)
        ):
            data = mic.stream.read(mic.config.chunk)
            frames.append(data)

        mic.close_stream()

        wav_io = io.BytesIO()
        wf = wave.open(wav_io, 'wb')
        wf.setnchannels(mic.config.channels)
        wf.setsampwidth(mic.sample_width)
        wf.setframerate(mic.config.rate)
        wf.writeframes(b''.join(frames))
        wf.close()

        return wav_io.getvalue()
