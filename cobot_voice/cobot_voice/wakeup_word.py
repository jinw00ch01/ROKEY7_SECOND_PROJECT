# 한국어 요약:
#   openwakeword 모델("hello_rokey")로 wakeword 검출을 수행하는 모듈.
#   마이크는 48kHz로 캡처되지만 openwakeword는 16kHz 입력을 요구하므로
#   scipy.signal.resample로 다운샘플링한다. confidence > 0.003이면 검출로
#   판정 — 매우 보수적인 threshold로 false negative를 줄이는 의도.
import os
import numpy as np
from openwakeword.model import Model
from scipy.signal import resample

from cobot_voice.env import get_package_path


package_path = str(get_package_path())
MODEL_NAME = "hello_rokey_8332_32.tflite"
MODEL_PATH = os.path.join(package_path, f"resource/{MODEL_NAME}")


class WakeupWord:
    def __init__(self, buffer_size):
        self.model = None
        self.model_name = MODEL_NAME.split(".", maxsplit=1)[0]
        self.stream = None
        self.buffer_size = buffer_size

    def is_wakeup(self):
        audio_chunk = np.frombuffer(
            self.stream.read(self.buffer_size, exception_on_overflow=False),
            dtype=np.int16,
        )
        # 48kHz 캡처를 openwakeword 입력 요건인 16kHz로 다운샘플링.
        audio_chunk = resample(audio_chunk, int(len(audio_chunk) * 16000 / 48000))
        outputs = self.model.predict(audio_chunk, threshold=0.1)
        confidence = outputs[self.model_name]
        print("confidence: ", confidence)
        # threshold 0.003은 매우 낮은 값 — 호출 누락(miss)을 줄이려는 보수적 설정.
        if confidence > 0.003:
            print("Wakeword detected!")
            return True
        return False

    def set_stream(self, stream):
        self.model = Model(wakeword_models=[MODEL_PATH])
        self.stream = stream
