# 🐳 ROKEY7_SECOND_PROJECT - OD Microservice Docker Guide

이 문서는 **Object Detection(OD) 전용 마이크로서비스**로 전환된 도커 환경 실행 가이드입니다. 음성 AI나 로봇 제어 기능은 제외하고, YOLO(ultralytics) 및 OpenCV 실행에 최적화된 경량화 버전을 제공합니다.

---

## 1. 초기 세팅 (최초 1회만 수행)

도커를 실행하기 전에 내 컴퓨터에 맞는 환경 변수를 설정해야 합니다.

1. 프로젝트 최상위 폴더에 있는 `.env.sample` 파일을 복사하여 `.env` 파일을 생성합니다.
   ```bash
   cp .env.sample .env
   ```
2. 생성한 `.env` 파일을 열고, 내 PC의 설정값(DISPLAY, NETWORK_INTERFACE 등)을 확인하여 수정합니다.
3. **GPU 사용자:** NVIDIA GPU를 사용하려면 호스트 PC에 [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)이 설치되어 있어야 합니다. 설치되어 있다면 별도 설정 없이 GPU 가속이 적용됩니다.

> **⚠️ 주의:** `.env` 파일은 절대 Github에 올리지 마세요! (이미 `.gitignore`에 처리되어 있습니다)

---

## 2. 도커 실행하기 (Build & Up)

환경 변수 세팅이 끝났다면, 아래 명령어로 도커를 빌드하고 백그라운드에서 실행합니다.

```bash
# 프로젝트 최상위 폴더(docker-compose.yml이 있는 곳)에서 실행
docker-compose up -d --build
```

- `-d`: 백그라운드 모드로 실행합니다.
- `--build`: `Dockerfile`이 변경되었을 때 최신 상태로 새로 빌드합니다.

---

## 3. 도커 컨테이너 접속 및 확인

컨테이너가 실행되면 자동으로 `cobot_object_detection od_node`가 실행되도록 설정되어 있습니다. 상태를 확인하거나 직접 명령을 내리려면 아래 명령어를 사용하세요.

### 컨테이너 쉘 접속
```bash
docker exec -it rokey7_od_container bash
```

### 실행 로그 확인
```bash
docker logs -f rokey7_od_container
```

---

## 4. 도커 종료하기

작업이 모두 끝났다면 아래 명령어로 도커를 종료합니다.

```bash
docker-compose down
```
