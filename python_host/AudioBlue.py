import sys
import struct
import threading
import queue
import serial
import numpy as np
import sounddevice as sd
import pyqtgraph as pg
from PyQt6.QtWidgets import QApplication

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
SERIAL_PORT = 'COMx'
BAUD_RATE = 460800
SAMPLE_RATE = 16000
BLOCK_SIZE = 512

print("\n--- AVAILABLE AUDIO DEVICES ---")
print(sd.query_devices())
try:
    MIC_ID = int(input("Enter the ID number of your Microphone: "))
except ValueError:
    sys.exit(1)

try:
    # write_timeout prevents python from freezing if the STM32 isn't reading
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1, write_timeout=0.5)
except Exception as e:
    print(f"Failed to open port {SERIAL_PORT}: {e}")
    sys.exit(1)

audio_tx_queue = queue.Queue()
fft_rx_queue = queue.Queue()

# ---------------------------------------------------------
# THREAD 1: AUDIO CAPTURE & TX (PC -> STM32)
# ---------------------------------------------------------
def audio_callback(indata, frames, time, status):
    pcm16 = (indata[:, 0] * 32767).astype(np.int16).tobytes()
    audio_tx_queue.put(pcm16)

def tx_thread():
    with sd.InputStream(device=MIC_ID, samplerate=SAMPLE_RATE, channels=1, dtype='float32', blocksize=BLOCK_SIZE, callback=audio_callback):
        while True:
            data = audio_tx_queue.get()
            try:
                ser.write(data)
            except Exception:
                pass

# ---------------------------------------------------------
# THREAD 2: SERIAL RX (STM32 -> PC)
# ---------------------------------------------------------
def rx_thread():
    sync_pattern = b'\xAA\xBB\xCC\xDD'
    buffer = bytearray()
    
    while True:
        try:
            # Pull everything currently sitting in the Windows USB buffer
            buffer += ser.read(max(1, ser.in_waiting))
            
            # Hunt for the 4-byte sync header sent by the STM32
            if sync_pattern in buffer:
                idx = buffer.find(sync_pattern)
                
                # Check if the full 256-byte payload has arrived yet (64 floats * 4 bytes)
                if len(buffer) >= idx + 4 + 256:
                    packet = buffer[idx+4 : idx+4+256]
                    
                    # Unpack raw binary into a Python tuple of 64 floats
                    fft_data = struct.unpack('<64f', packet)
                    
                    # Clear queue to ensure we only graph the freshest frame
                    while not fft_rx_queue.empty():
                        try: fft_rx_queue.get_nowait()
                        except: pass
                        
                    fft_rx_queue.put(fft_data)
                    
                    # Slice the buffer to remove the processed packet
                    buffer = buffer[idx+4+256:]
                else:
                    # Drop old junk data before the sync pattern to save memory
                    buffer = buffer[idx:]
        except Exception:
            pass

# Start the background communication threads
threading.Thread(target=tx_thread, daemon=True).start()
threading.Thread(target=rx_thread, daemon=True).start()

# ---------------------------------------------------------
# MAIN THREAD: PYQTGRAPH GUI
# ---------------------------------------------------------
app = QApplication(sys.argv)
win = pg.GraphicsLayoutWidget(show=True, title="STM32 Hardware Spectrum Analyzer")
win.resize(1000, 600)

plot = win.addPlot(title="Real-Time Frequency Spectrum (0 - 8 kHz)")
plot.setYRange(0, 15000)   # Adjust this max height based on your mic sensitivity
plot.setXRange(0, 8000)
plot.setLabel('left', 'Linear Amplitude')
plot.setLabel('bottom', 'Frequency', units='Hz')
plot.showGrid(x=True, y=True, alpha=0.3)

# Create 64 bins mapped to their exact center frequencies
x_freqs = np.linspace(0, 8000, 64)
bar_graph = pg.BarGraphItem(x=x_freqs, height=np.zeros(64), width=100, brush='c')
plot.addItem(bar_graph)

# GUI Update Loop (~30 FPS)
def update_gui():
    try:
        # Grab the newest FFT array from the RX thread
        new_fft_data = fft_rx_queue.get_nowait()
        
        # Overwrite the bars with the new heights
        bar_graph.setOpts(height=new_fft_data)
    except queue.Empty:
        pass

# Trigger the GUI update every 30 milliseconds
from PyQt6.QtCore import QTimer
timer = QTimer()
timer.timeout.connect(update_gui)
timer.start(30)

if __name__ == '__main__':
    # Reminder: Flash STM32 and hit Resume in debugger BEFORE running this!
    sys.exit(app.exec())