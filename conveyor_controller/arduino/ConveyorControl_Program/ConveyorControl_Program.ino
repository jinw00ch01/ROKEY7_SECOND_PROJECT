/*
  ConveyorControl_Program

  Serial protocol used by the ROS 2 conveyor_controller package:
    F30   run forward at 30 percent speed
    R30   run reverse at 30 percent speed
    STOP  stop the conveyor

  Hardware target: Arduino UNO connected to a STEP/DIR stepper driver
  such as A4988, DRV8825, TB6600, or similar.
*/

const unsigned long BAUD_RATE = 115200;

const byte STEP_PIN = 2;
const byte DIR_PIN = 3;
const byte ENABLE_PIN = 4;

const bool ENABLE_ACTIVE_LOW = true;
const bool FORWARD_DIR_LEVEL = HIGH;

const unsigned int MIN_SPEED_PERCENT = 1;
const unsigned int MAX_SPEED_PERCENT = 100;
const unsigned long MAX_STEP_RATE_HZ = 1200;
const unsigned int STEP_PULSE_US = 5;
const unsigned long COMMAND_TIMEOUT_MS = 0;  // Set > 0 to auto-stop on silence.

String inputLine;
bool running = false;
bool directionForward = true;
unsigned int speedPercent = 30;
unsigned long stepIntervalUs = 1000000UL / MAX_STEP_RATE_HZ;
unsigned long lastStepUs = 0;
unsigned long lastCommandMs = 0;

void setDriverEnabled(bool enabled) {
  if (ENABLE_ACTIVE_LOW) {
    digitalWrite(ENABLE_PIN, enabled ? LOW : HIGH);
  } else {
    digitalWrite(ENABLE_PIN, enabled ? HIGH : LOW);
  }
}

void updateStepInterval() {
  unsigned long stepRate = (MAX_STEP_RATE_HZ * (unsigned long)speedPercent) / 100UL;
  if (stepRate < 1UL) {
    stepRate = 1UL;
  }
  stepIntervalUs = 1000000UL / stepRate;
}

void stopConveyor() {
  running = false;
  setDriverEnabled(false);
}

void startConveyor(bool forward, unsigned int percent) {
  directionForward = forward;
  speedPercent = constrain(percent, MIN_SPEED_PERCENT, MAX_SPEED_PERCENT);
  updateStepInterval();

  digitalWrite(DIR_PIN, directionForward ? FORWARD_DIR_LEVEL : !FORWARD_DIR_LEVEL);
  setDriverEnabled(true);
  running = true;
  lastCommandMs = millis();
}

bool parseSpeedPercent(const String &command, unsigned int &percent) {
  if (command.length() < 2) {
    return false;
  }

  long parsed = command.substring(1).toInt();
  if (parsed < MIN_SPEED_PERCENT || parsed > MAX_SPEED_PERCENT) {
    return false;
  }

  percent = (unsigned int)parsed;
  return true;
}

void handleCommand(String command) {
  command.trim();
  command.toUpperCase();

  if (command == "STOP") {
    stopConveyor();
    Serial.println("OK STOP");
    return;
  }

  char mode = command.charAt(0);
  if (mode == 'F' || mode == 'R') {
    unsigned int percent = 0;
    if (!parseSpeedPercent(command, percent)) {
      Serial.println("ERR SPEED");
      return;
    }

    startConveyor(mode == 'F', percent);
    Serial.print("OK ");
    Serial.println(command);
    return;
  }

  Serial.println("ERR COMMAND");
}

void readSerialCommands() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();

    if (c == '\n') {
      handleCommand(inputLine);
      inputLine = "";
    } else if (c != '\r') {
      inputLine += c;
      if (inputLine.length() > 16) {
        inputLine = "";
        Serial.println("ERR TOO_LONG");
      }
    }
  }
}

void runStepper() {
  if (!running) {
    return;
  }

  if (COMMAND_TIMEOUT_MS > 0 && millis() - lastCommandMs > COMMAND_TIMEOUT_MS) {
    stopConveyor();
    Serial.println("WARN TIMEOUT_STOP");
    return;
  }

  unsigned long nowUs = micros();
  if (nowUs - lastStepUs >= stepIntervalUs) {
    lastStepUs = nowUs;
    digitalWrite(STEP_PIN, HIGH);
    delayMicroseconds(STEP_PULSE_US);
    digitalWrite(STEP_PIN, LOW);
  }
}

void setup() {
  pinMode(STEP_PIN, OUTPUT);
  pinMode(DIR_PIN, OUTPUT);
  pinMode(ENABLE_PIN, OUTPUT);

  digitalWrite(STEP_PIN, LOW);
  digitalWrite(DIR_PIN, FORWARD_DIR_LEVEL);
  stopConveyor();

  Serial.begin(BAUD_RATE);
  Serial.println("READY CONVEYOR");
}

void loop() {
  readSerialCommands();
  runStepper();
}
