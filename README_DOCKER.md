# 🐳 ROKEY7_SECOND_PROJECT - Docker Development Guide

이 문서는 다양한 OS(Windows WSL, Ubuntu) 및 하드웨어 사양(NVIDIA GPU, 사운드 카드)을 가진 팀원들이 동일한 환경에서 충돌 없이 개발할 수 있도록 구축된 **도커 환경 실행 가이드**입니다.

---

## 1. 초기 세팅 (최초 1회만 수행)

도커를 실행하기 전에 내 컴퓨터에 맞는 환경 변수를 설정해야 합니다.

1. 프로젝트 최상위 폴더에 있는 `.env.sample` 파일을 복사하여 `.env` 파일을 생성합니다.
   ```bash
   cp .env.sample .env
   ```
2. 생성한 `.env` 파일을 열고, 주석에 적힌 **'확인 명령어'**를 터미널에 입력하여 내 PC의 설정값을 찾습니다.
3. **GPU 설정:** 내 컴퓨터에 NVIDIA GPU가 없다면 `COMPOSE_PROFILES=cpu`, 있다면 `gpu`로 설정합니다.
4. 찾은 값을 `.env`에 알맞게 수정하고 저장합니다.

> **⚠️ 주의:** `.env` 파일은 절대 Github에 올리지 마세요! (이미 `.gitignore`에 처리되어 있습니다)

---

## 2. 도커 실행하기 (Build & Up)

환경 변수 세팅이 끝났다면, 아래 명령어로 도커를 빌드하고 백그라운드에서 실행합니다.

```bash
# 프로젝트 최상위 폴더(docker-compose.yml이 있는 곳)에서 실행
docker-compose up -d --build
```

- `-d`: 백그라운드 모드로 실행하여 터미널을 계속 사용할 수 있게 합니다.
- `--build`: `Dockerfile`이 변경되었을 때 최신 상태로 새로 빌드합니다. (이후에는 `docker-compose up -d`만 쳐도 됩니다.)

---

## 3. 도커 컨테이너 접속 (실무 돌입!)

컨테이너가 켜졌다면, 이제 컨테이너 안으로 들어가서 진짜 작업을 시작할 차례입니다.

```bash
docker exec -it rokey7_dev_container bash
```

- 접속하면 `root@호스트이름:/home/ros2_ws#` 형태로 터미널이 바뀝니다.
- 여기서 평소처럼 `colcon build`, `ros2 launch` 등을 실행하시면 됩니다!
- 코드를 에디터(VSCode 등)로 밖에서 수정하면 도커 안에도 **실시간으로 반영**됩니다. (볼륨 동기화)

---

## 4. 🛠️ 시각적 도커 관리: Portainer 접속

터미널 명령어가 익숙하지 않거나 현재 켜져 있는 도커 컨테이너들의 상태, 로그를 눈으로 보고 싶다면 **Portainer**를 사용하세요.

1. 웹 브라우저를 열고 주소창에 아래를 입력합니다.
   👉 **http://localhost:9443** (또는 http://127.0.0.1:9443)
2. 최초 접속 시 관리자 비밀번호를 설정합니다.
3. **[Get Started]** -> **[Local]** 환경을 선택하면 현재 실행 중인 `rokey7_dev_container`를 쉽게 관리할 수 있습니다!

---

## 5. 도커 종료하기

작업이 모두 끝났고 컴퓨터 자원을 아끼고 싶다면 아래 명령어로 도커를 종료합니다.

```bash
docker-compose down
```
