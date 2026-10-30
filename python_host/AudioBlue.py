
import sys
import struct
import threading
import queue
import time

import serial
import numpy as np
import sounddevice as sd
import pyqtgraph as pg

from PyQt5.QtWidgets import QApplication


# =========================================================
# CONFIGURATION
# =========================================================

SERIAL_PORT = "COM10"
BAUD_RATE = 460800

SAMPLE_RATE = 16000
BLOCK_SIZE = 512

FFT_SIZE = 128
FFT_BINS = 64
BIN_WIDTH = SAMPLE_RATE / FFT_SIZE  # 125 Hz

SYNC_WORD = b"\xAA\xBB\xCC\xDD"
PACKET_SIZE = 4 + FFT_BINS * 4

# Speech detection settings
SPEECH_GATE = 100.0
BIN_THRESHOLD = 100.0
RELATIVE_THRESHOLD = 0.10

SILENCE_DURATION = 1.0
MIN_SPEECH_FRAMES = 5

# Queues
audio_queue = queue.Queue(maxsize=20)
fft_queue = queue.Queue(maxsize=200)

# Session variables
speech_active = False
last_voice_time = 0

session_power_sum = np.zeros(FFT_BINS, dtype=np.float64)
session_frame_count = 0

session_low_bins = []
session_high_bins = []

# Last calculated values
last_bandwidth = None
last_3db_bandwidth = None
last_obw_99 = None


# =========================================================
# MICROPHONE CALLBACK
# =========================================================

def audio_callback(indata, frames, time_info, status):

    if status:
        print("Audio status:", status)

    audio = np.clip(indata[:, 0], -1.0, 1.0)

    audio_int16 = (audio * 32767).astype(np.int16)

    try:
        audio_queue.put_nowait(audio_int16.tobytes())
    except queue.Full:
        pass


# =========================================================
# TRANSMIT MICROPHONE DATA TO STM32
# =========================================================

def tx_thread(ser):

    print("Microphone transmission started.")

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            channels=1,
            dtype="float32",
            callback=audio_callback
        ):

            while True:

                audio_data = audio_queue.get()

                ser.write(audio_data)

    except Exception as e:
        print("TX error:", e)


# =========================================================
# RECEIVE FFT DATA FROM STM32
# =========================================================

def rx_thread(ser):

    print("FFT reception started.")

    buffer = bytearray()

    while True:

        try:

            buffer.extend(ser.read(max(1, ser.in_waiting)))

            while True:

                sync_index = buffer.find(SYNC_WORD)

                if sync_index < 0:

                    # Retain the last few bytes in case
                    # the sync word is split across reads.
                    if len(buffer) > 3:
                        del buffer[:-3]

                    break

                if sync_index > 0:
                    del buffer[:sync_index]

                if len(buffer) < PACKET_SIZE:
                    break

                packet = buffer[:PACKET_SIZE]
                del buffer[:PACKET_SIZE]

                fft_data = struct.unpack(
                    "<64f",
                    packet[4:]
                )

                fft_data = np.array(fft_data, dtype=np.float32)

                try:
                    fft_queue.put_nowait(fft_data)

                except queue.Full:
                    try:
                        fft_queue.get_nowait()
                    except queue.Empty:
                        pass

                    fft_queue.put_nowait(fft_data)

        except Exception as e:
            print("RX error:", e)
            time.sleep(0.1)


# =========================================================
# FREQUENCY INTERPOLATION
# =========================================================

def interpolate_crossing(x1, y1, x2, y2, target):

    if y2 == y1:
        return (x1 + x2) / 2

    return x1 + (target - y1) * (x2 - x1) / (y2 - y1)


# =========================================================
# CALCULATE -3 dB BANDWIDTH
# =========================================================

def calculate_3db_bandwidth(power):

    # Ignore DC bin
    p = power[1:]

    if len(p) == 0 or np.max(p) <= 0:
        return None, None, None

    peak_index = np.argmax(p) + 1
    peak_power = power[peak_index]

    # -3 dB means half the peak power
    threshold = peak_power / 2.0

    left = peak_index
    right = peak_index

    # Find left edge around the strongest peak
    while left > 1 and power[left - 1] >= threshold:
        left -= 1

    # Find right edge around the strongest peak
    while right < FFT_BINS - 1 and power[right + 1] >= threshold:
        right += 1

    # Interpolate the left crossing
    if left > 1:

        low_freq = interpolate_crossing(
            (left - 1) * BIN_WIDTH,
            power[left - 1],
            left * BIN_WIDTH,
            power[left],
            threshold
        )

    else:
        low_freq = left * BIN_WIDTH

    # Interpolate the right crossing
    if right < FFT_BINS - 1:

        high_freq = interpolate_crossing(
            right * BIN_WIDTH,
            power[right],
            (right + 1) * BIN_WIDTH,
            power[right + 1],
            threshold
        )

    else:
        high_freq = right * BIN_WIDTH

    bandwidth = high_freq - low_freq

    return low_freq, high_freq, bandwidth


# =========================================================
# CALCULATE 99% OCCUPIED BANDWIDTH
# =========================================================

def calculate_99_obw(power):

    # Ignore DC
    p = power[1:].copy()

    total_power = np.sum(p)

    if total_power <= 0:
        return None, None, None

    frequencies = np.arange(1, FFT_BINS) * BIN_WIDTH

    cumulative_power = np.cumsum(p) / total_power

    # 99% OBW:
    # 0.5% power below the lower edge
    # 0.5% power above the upper edge

    low_freq = np.interp(
        0.005,
        cumulative_power,
        frequencies
    )

    high_freq = np.interp(
        0.995,
        cumulative_power,
        frequencies
    )

    bandwidth = high_freq - low_freq

    return low_freq, high_freq, bandwidth


# =========================================================
# FINISH SPEECH SESSION
# =========================================================

def finish_speech_session():

    global speech_active
    global session_power_sum
    global session_frame_count
    global session_low_bins
    global session_high_bins

    global last_bandwidth
    global last_3db_bandwidth
    global last_obw_99

    speech_active = False

    if session_frame_count < MIN_SPEECH_FRAMES:

        print("Speech session too short.")

        session_power_sum[:] = 0
        session_frame_count = 0
        session_low_bins.clear()
        session_high_bins.clear()

        return

    # Average power spectrum across the entire session
    average_power = session_power_sum / session_frame_count

    # -----------------------------------------------------
    # 1. Original session bandwidth estimate
    # -----------------------------------------------------

    low_bin = int(np.percentile(session_low_bins, 10))
    high_bin = int(np.percentile(session_high_bins, 90))

    low_freq = low_bin * BIN_WIDTH
    high_freq = high_bin * BIN_WIDTH

    last_bandwidth = high_freq - low_freq

    # -----------------------------------------------------
    # 2. -3 dB bandwidth
    # -----------------------------------------------------

    db_low, db_high, last_3db_bandwidth = (
        calculate_3db_bandwidth(average_power)
    )

    # -----------------------------------------------------
    # 3. 99% Occupied Bandwidth
    # -----------------------------------------------------

    obw_low, obw_high, last_obw_99 = (
        calculate_99_obw(average_power)
    )

    # -----------------------------------------------------
    # Display results
    # -----------------------------------------------------

    print("\n========== SPEECH SESSION RESULTS ==========")

    print(
        f"Session bandwidth: {last_bandwidth:.1f} Hz"
    )

    if last_3db_bandwidth is not None:

        print(
            f"-3 dB bandwidth: {last_3db_bandwidth:.1f} Hz"
        )

        print(
            f"-3 dB range: {db_low:.1f} - {db_high:.1f} Hz"
        )

    if last_obw_99 is not None:

        print(
            f"99% OBW: {last_obw_99:.1f} Hz"
        )

        print(
            f"99% OBW range: {obw_low:.1f} - {obw_high:.1f} Hz"
        )

    print("============================================\n")

    # Reset session data for the next speaking session
    session_power_sum[:] = 0
    session_frame_count = 0

    session_low_bins.clear()
    session_high_bins.clear()


# =========================================================
# PROCESS EACH FFT FRAME
# =========================================================

def process_fft_frame(fft_data):

    global speech_active
    global last_voice_time

    global session_power_sum
    global session_frame_count

    global session_low_bins
    global session_high_bins

    magnitudes = np.abs(fft_data)

    if not np.all(np.isfinite(magnitudes)):
        return

    peak_amp = np.max(magnitudes)

    # Detect speech
    if peak_amp >= SPEECH_GATE:

        if not speech_active:

            speech_active = True

            session_power_sum[:] = 0
            session_frame_count = 0

            session_low_bins.clear()
            session_high_bins.clear()

            print("\nSpeech detected. Analysing...")

        last_voice_time = time.monotonic()

        # Convert magnitude spectrum to power spectrum
        power = magnitudes.astype(np.float64) ** 2

        session_power_sum += power
        session_frame_count += 1

        # Preserve original session bandwidth calculation
        threshold = max(
            BIN_THRESHOLD,
            peak_amp * RELATIVE_THRESHOLD
        )

        active_bins = np.where(magnitudes >= threshold)[0]

        if len(active_bins) > 0:

            session_low_bins.append(active_bins[0])
            session_high_bins.append(active_bins[-1])


# =========================================================
# GUI UPDATE
# =========================================================

def update_gui():

    global speech_active

    # Process available FFT frames
    while True:

        try:
            fft_data = fft_queue.get_nowait()

        except queue.Empty:
            break

        # Update graph
        magnitudes = np.abs(fft_data)

        bar_graph.setOpts(height=magnitudes)

        process_fft_frame(fft_data)

    # Detect end of speech
    if speech_active:

        elapsed = time.monotonic() - last_voice_time

        if elapsed >= SILENCE_DURATION:

            finish_speech_session()

            plot.setTitle(
                f"Session BW: {last_bandwidth:.1f} Hz | "
                f"-3 dB BW: {last_3db_bandwidth:.1f} Hz | "
                f"99% OBW: {last_obw_99:.1f} Hz"
            )


# =========================================================
# MAIN PROGRAM
# =========================================================

def main():

    global bar_graph
    global plot

    print("Connecting to STM32...")

    try:

        ser = serial.Serial(
            SERIAL_PORT,
            BAUD_RATE,
            timeout=0.1
        )

    except Exception as e:

        print("Serial connection failed:", e)
        return

    print("Connected to", SERIAL_PORT)

    # Start communication threads
    threading.Thread(
        target=tx_thread,
        args=(ser,),
        daemon=True
    ).start()

    threading.Thread(
        target=rx_thread,
        args=(ser,),
        daemon=True
    ).start()

    # Create GUI
    app = QApplication(sys.argv)

    window = pg.GraphicsLayoutWidget(
        show=True,
        title="STM32 Voice Spectrum Analyser"
    )

    plot = window.addPlot(
        title="Speak into the microphone..."
    )

    plot.setLabel("left", "Magnitude")
    plot.setLabel("bottom", "Frequency", units="Hz")

    plot.setXRange(0, 8000)

    frequencies = np.arange(FFT_BINS) * BIN_WIDTH

    bar_graph = pg.BarGraphItem(
        x=frequencies,
        height=np.zeros(FFT_BINS),
        width=BIN_WIDTH * 0.8
    )

    plot.addItem(bar_graph)

    # Update GUI every 30 milliseconds
    timer = pg.QtCore.QTimer()

    timer.timeout.connect(update_gui)
    timer.start(30)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
