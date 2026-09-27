import sounddevice as sd  # Captures audio from the microphone
import serial             # Handles UART communication over USB
import numpy as np        # Used for fast array math and type conversion
import queue              # Thread-safe queue to pass data between threads
import sys                # System-level commands (like exiting on error)

# ---------------------------------------------------------
# 1. AUDIO DEVICE SELECTION
# Print all available audio inputs to the terminal so the 
# user can identify the correct microphone ID.
# ---------------------------------------------------------
print("\n--- AVAILABLE AUDIO DEVICES ---")
print(sd.query_devices())
print("-------------------------------\n")

try:
    # Prompt the user to type the ID of the microphone they want to stream
    mic_id_input = input("Enter the ID number of your Nord Buds Microphone: ")
    MIC_ID = int(mic_id_input)
except ValueError:
    print("Invalid ID. Exiting.")
    sys.exit(1)

# ---------------------------------------------------------
# 2. HARDWARE CONFIGURATION
# ---------------------------------------------------------
SERIAL_PORT = 'COMx'       # MUST match the ST-LINK Virtual COM port in Device Manager
BAUD_RATE   = 460800       # High-speed baud rate matching the STM32 USART2 configuration
SAMPLE_RATE = 16000        # 16 kHz sample rate (standard for voice audio)
BLOCK_SIZE  = 512          # Number of audio frames processed at a time

# Create a thread-safe queue. This is critical because writing to a USB serial 
# port is slow. The queue prevents the slow USB write from blocking the fast 
# microphone capture, which avoids "Input Overflow" errors.
audio_queue = queue.Queue()

# ---------------------------------------------------------
# 3. INITIALIZE SERIAL CONNECTION
# ---------------------------------------------------------
try:
    # Open the serial port with a slight timeout to prevent infinite blocking
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
except Exception as e:
    print(f"Failed to open {SERIAL_PORT}: {e}")
    sys.exit(1)

# ---------------------------------------------------------
# 4. AUDIO CAPTURE CALLBACK
# This function is automatically called by the sounddevice 
# library in a background C-thread every time 'BLOCK_SIZE' 
# audio frames are recorded. It must execute instantly.
# ---------------------------------------------------------
def audio_callback(indata, frames, time, status):
    # 'indata' comes in as float32 decimal values between -1.0 and 1.0.
    # We multiply by 32767 to scale it, convert to 16-bit signed integers (PCM),
    # and then convert the array into a raw binary string of bytes.
    pcm16_data = (indata[:, 0] * 32767).astype(np.int16).tobytes()
    
    # Toss the raw bytes into the queue and exit instantly so the mic can keep recording
    audio_queue.put(pcm16_data)

# ---------------------------------------------------------
# 5. MAIN EXECUTION LOOP
# ---------------------------------------------------------
try:
    print(f"\nStreaming Mic ID {MIC_ID} to STM32 on {SERIAL_PORT}...")
    
    # Start the audio stream. This opens the microphone and spawns a background 
    # thread that continuously feeds the 'audio_callback' function.
    with sd.InputStream(device=MIC_ID, 
                        samplerate=SAMPLE_RATE, 
                        channels=1, 
                        dtype='float32', 
                        blocksize=BLOCK_SIZE, 
                        callback=audio_callback):
        
        # This is the main thread. Its only job is to wait for data to appear 
        # in the queue and blast it over the UART cable as fast as possible.
        while True:
            data_chunk = audio_queue.get()  # Block until data is available in the queue
            ser.write(data_chunk)           # Send the binary chunk to the STM32
            
except KeyboardInterrupt:
    # Catch Ctrl+C to cleanly stop the stream without throwing an ugly error trace
    print("\nStreaming stopped.")
finally:
    # Always ensure the serial port is closed on exit so it doesn't stay locked in Windows
    if 'ser' in locals() and ser.is_open:
        ser.close()