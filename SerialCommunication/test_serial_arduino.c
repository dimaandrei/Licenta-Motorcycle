void setup() {
  Serial1.begin(115200);
  Serial.begin(115200);
}

void loop() {
   if (Serial1.available() > 0) {
    String data = Serial1.readStringUntil('\n');
    Serial1.print("You sent me: ");
    Serial1.println(data);
    Serial.print("You sent me: ");
    Serial.println(data);
  }
}
