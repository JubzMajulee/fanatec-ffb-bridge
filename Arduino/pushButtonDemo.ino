// Define the button pin as A0
const int buttonPin = A0;

// Variable to track the state change
int lastButtonState = HIGH; 

void setup() {
  // Initialize serial communication
  Serial.begin(9600);
  
  // A0 supports INPUT_PULLUP just like digital pins
  pinMode(buttonPin, INPUT_PULLUP);
}

void loop() {
  // Read the current state of A0
  int currentButtonState = digitalRead(buttonPin);

  // Check if the button state has changed
  if (currentButtonState != lastButtonState) {
    
    // If the state is LOW, the button is pressed
    if (currentButtonState == LOW) {
      Serial.println("Arduino||1");
    } 
    // If the state is HIGH, the button is released
    else {
      Serial.println("Arduino||0");
    }
    
    // Update the last state
    lastButtonState = currentButtonState;
    
    // Small delay to debounce
    delay(50);
  }
}