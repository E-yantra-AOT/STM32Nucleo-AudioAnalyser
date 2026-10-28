# STM32-AudioAnalyser

A robust, real-time embedded DSP pipeline that captures live microphone audio from a PC, streams it as 16-bit PCM data over high-speed UART to an STM32 Nucleo-F103RB, and performs on-chip digital filtering and 128-point FFT spectrum analysis.

This project bypasses external analog pre-amplifier circuitry by utilizing the PC's sound card as the ADC, funneling digitized audio into the STM32's circular buffer for real-time Exponential Moving Average (EMA) low-pass filtering, Hanning windowing, and frequency-domain extraction.

## 🚀 Current Features

- **Live Audio Capture:** Uses Python to grab real-time audio from any PC-connected microphone (analog or Bluetooth).
- **High-Speed Serial Streaming:** Transmits 16-bit PCM data over a Virtual COM Port at 460,800 baud.
- **Non-Blocking Architecture:** Thread-safe queueing and serial write timeouts (`write_timeout=0.5`) on the Python host ensure the microphone never drops frames or locks the OS kernel if the MCU is paused.
- **Interrupt-Driven Ring Buffer:** The STM32 utilizes an asynchronous circular buffer (4096 bytes) to catch continuous audio data without halting the main CPU loop.
- **Bulletproof Error Recovery:** Custom hardware-level register resets prevent the STM32 from freezing during Overrun (ORE) or Framing errors caused by heavy interrupt loads.
- **1st-Order IIR Low-Pass Filter:** Implements a single-pole Exponential Moving Average (EMA) digital filter ($\alpha = 0.28$, $f_c \approx 1\text{ kHz}$) to strip high-frequency ambient noise and sibilance before spectral analysis.
- **On-Chip 128-Point Radix-2 FFT:** Applies a Hanning window to 128-sample blocks and computes an in-place Cooley-Tukey FFT with $N/2$ linear amplitude normalization ($125\text{ Hz}$ bin resolution, $\sim 8.5\text{ ms}$ total latency).

## 🛠️ Tools & Hardware Required

### Hardware

- STM32 Nucleo-F103RB Development Board
- PC with an audio input device (Analog Mic / Headset / Earbuds)
- Mini-USB to USB-A cable (for ST-LINK programming and serial communication)

### Software

- **Hardware Configuration:** [STM32CubeMX](https://www.st.com/en/development-tools/stm32cubemx.html) (Standalone)
- **IDE & Toolchain:** [STM32CubeIDE 2.0+](https://www.st.com/en/development-tools/stm32cubeide.html)
- **Environment:** Python 3.8+
- **Python Libraries:** `sounddevice`, `pyserial`, `numpy`

## 📂 Repository Structure

```text
STM32Nucleo-AudioAnalyser/
├── python_host/
│   └── AudioBlue.py                # Main audio capture and UART streaming script
├── stm32_firmware/
│   ├── Core/                       # Main C DSP pipeline (main.c, ring buffer, IIR filter, FFT)
│   ├── Drivers/                    # STM32 HAL and CMSIS drivers
│   ├── AudioSIgnalAnalyser.ioc     # Standalone STM32CubeMX configuration file
│   └── .project / .cproject        # STM32CubeIDE project files
├── requirements.txt                # Python dependencies
├── .gitignore
└── README.md
```

## ⚙️ Installation & Setup

### 1. STM32 Firmware Setup

1. Clone this repository to your local machine.
2. Open **STM32CubeIDE**.
3. Go to: `File → Open Projects from File System...`
4. Select the `stm32_firmware` folder.
5. Open: `Core/Src/main.c`
   - The firmware is already configured to use USART2 with global interrupts enabled.
6. Build the project using the **Hammer Icon** to ensure there are no compilation errors.
7. Connect the STM32 Nucleo-F103RB to your PC using the USB connection associated with the ST-LINK interface.
8. Click **Debug** to flash the firmware onto the STM32, then press **Resume (`F8`)** so the CPU actively runs past `HAL_Init()` and arms the UART RX interrupt before starting the Python stream.

### 2. Python Host Setup

1. Open a terminal.
2. Navigate to the `python_host` directory:
   ```bash
   cd python_host
   ```
3. Create a virtual environment (optional but recommended):
   ```bash
   python -m venv env
   ```
4. Activate the virtual environment.

   Windows:
   ```bash
   env\Scripts\activate
   ```
5. Install the required Python dependencies (from the root directory or using `..`):
   ```bash
   pip install -r ../requirements.txt
   ```
6. Open **Device Manager** on Windows.
7. Locate the ST-LINK Virtual COM Port and note its COM port number.

   Example: `COM3`
8. Open: `AudioBlue.py`
9. Update the `SERIAL_PORT` variable to match the COM port assigned to the STM32.

   Example:
   ```python
   SERIAL_PORT = "COM3"
   ```

## 🏃‍♂️ Running the Bridge

Ensure that:

- The STM32 Nucleo-F103RB is connected to the PC.
- The STM32 firmware has been successfully flashed.
- The correct ST-LINK Virtual COM Port is configured in `AudioBlue.py`.
- The Python virtual environment is activated, if one was created.

Navigate to the `python_host` directory and run:

```bash
python AudioBlue.py
```

The script will print a list of available audio devices.

Example:

```text
Available Audio Devices:

0: Microsoft Sound Mapper - Input
1: Microphone
2: Headset Microphone
3: Bluetooth Earbuds
...
```

Identify the microphone you want to use and enter its corresponding device ID when prompted.

Speak into the microphone.

The Python application will:

1. Capture live microphone audio.
2. Convert the incoming samples into 16-bit PCM data.
3. Place the audio data into a thread-safe queue.
4. Continuously transmit the queued audio data through the serial interface.
5. Send the data to the STM32 through USART2.
6. Allow the STM32 interrupt-driven receiver to process the incoming byte stream.
7. Store the received bytes inside the STM32 ring buffer.
8. Pop 256-byte chunks (128 samples) from the ring buffer and reconstruct Little-Endian 16-bit signed PCM integers.
9. Filter each sample through the 1st-order IIR Low-Pass Filter ($\alpha = 0.28$, $f_c \approx 1\text{ kHz}$).
10. Apply a 128-point Hanning window to suppress spectral leakage and execute the in-place Radix-2 Cooley-Tukey FFT.
11. Normalize the complex magnitudes by $N/2$ ($64.0$) into `fft_magnitudes[64]` for real-time inspection.

## ✅ Verification

**LD1 — ST-LINK USB Activity**

The LD1 USB/status LED may flicker rapidly while data is being transferred through the ST-LINK Virtual COM interface.

This indicates USB/serial activity between the PC and the development board.

**LD2 — STM32 UART Reception**

The LD2 LED will flicker rapidly when configured by the firmware to indicate successful UART reception.

This confirms that the STM32 is:

- Receiving UART data.
- Triggering UART interrupts.
- Processing the received bytes.
- Pushing the data into the ring buffer.

**STM32CubeIDE — Live Expressions**

While in a Debug session with the MCU running, open the **Live Expressions** tab and monitor:
- `fft_magnitudes` (`float[64]`): Real-time normalized linear amplitudes across 64 frequency bins ($0\text{ Hz}$ to $7875\text{ Hz}$ in $125\text{ Hz}$ steps). Bins above index `[8]` ($>1\text{ kHz}$) remain heavily attenuated by the IIR filter.
- `max_fft_observed` (`float`): Tracks the highest normalized peak amplitude observed (scaled to the $0\text{–}32,767$ PCM16 range).
- `lpf_prev_output` (`float`): Current state of the 1st-order IIR low-pass filter.
- `audio_fifo` (`RingBuffer`): Inspect `head` and `tail` pointers to verify zero-overflow synchronization.

## 🔄 Data Pipeline

The complete data flow is:

```text
Microphone
    │
    ▼
PC Sound Card / Audio Driver
    │
    ▼
Python + sounddevice
    │
    ▼
16-bit PCM Audio Samples
    │
    ▼
Thread-Safe Queue
    │
    ▼
Python + pyserial
    │
    ▼
USB / ST-LINK Virtual COM Port
    │
    ▼
USART2 @ 460800 Baud
    │
    ▼
STM32 UART Interrupt
    │
    ▼
UART Error Handling
    │
    ▼
4096-Byte Ring Buffer
    │
    ▼
256-Byte Block Pop & 16-Bit Little-Endian PCM Reconstruction
    │
    ▼
1st-Order IIR Low-Pass Filter (alpha = 0.28, fc ≈ 1 kHz)
    │
    ▼
128-Point Hanning Window
    │
    ▼
128-Point Radix-2 Cooley-Tukey FFT & N/2 Normalization
    │
    ▼
fft_magnitudes[64] (STM32CubeIDE Live Expressions)
```

## 🧠 Technical Deep Dive: The Overrun Trap

Streaming audio at 16 kHz with 16-bit samples generates approximately:

```text
16,000 samples/second × 2 bytes/sample
= 32,000 bytes/second
```

Therefore, the STM32 must continuously receive approximately 32 KB/s of raw audio data.

The UART is configured at:

**Baud Rate:** 460,800 baud

At this data rate, the STM32 can experience a very high interrupt frequency because the receiver must continuously process incoming UART bytes.

### UART Overrun Error

A UART Overrun Error (ORE) occurs when a new byte arrives before the previous received byte has been properly serviced.

Conceptually:

```text
Byte N arrives
     │
     ▼
UART Data Register
     │
     │ CPU must read it
     ▼
Byte N processed
     │
     ▼
Byte N+1 arrives
```

If the CPU fails to service the UART quickly enough:

```text
Byte N arrives
     │
     ▼
UART Data Register
     │
     │ CPU is delayed
     ▼
Byte N+1 arrives
     │
     ▼
ORE FLAG
```

An uncleared UART error can cause the receiver to stop behaving as expected, interrupting the continuous audio stream.

## 🛡️ Hardware-Level Error Recovery

This project implements custom UART error recovery rather than relying entirely on the default HAL behavior.

Inside:

```c
HAL_UART_ErrorCallback()
```

the firmware manually accesses the STM32 UART status and data registers.

The relevant registers include:

- **SR** — Status Register
- **DR** — Data Register

The recovery process is conceptually:

```text
UART Error
    │
    ▼
HAL_UART_ErrorCallback()
    │
    ▼
Read UART Status Register
    │
    ▼
Read UART Data Register
    │
    ▼
Clear Physical Error Condition
    │
    ▼
Re-arm UART Reception
    │
    ▼
Continue Receiving Audio
```

This prevents a temporary UART error from permanently stopping the audio reception pipeline.

## 🔁 Interrupt-Driven Ring Buffer

The STM32 uses a 4096-byte circular/ring buffer to decouple UART reception from main-loop DSP processing.

Instead of forcing the main application to process every byte immediately:

```text
UART Interrupt
      │
      ▼
Receive Byte
      │
      ▼
Ring Buffer
      │
      ▼
Main Application
      │
      ▼
DSP Processing
```

The UART interrupt remains responsible for receiving the data, while the main application can process buffered data independently.

### Ring Buffer Concept

The buffer contains:

```text
+----+----+----+----+-----+-----+
| 00 | 01 | 02 | 03 | ... |4095|
+----+----+----+----+-----+-----+
  ↑
Read Pointer

                    ↑
                  Write Pointer
```

- The write pointer advances whenever a new byte is received.
- The read pointer advances whenever the main application consumes a byte.
- When either pointer reaches the end of the buffer, it wraps back to the beginning.

This allows the buffer to operate continuously without moving the entire contents of memory.

## 🎧 Audio Format

The current system streams audio as:

| Parameter          | Value                         |
|--------------------|-------------------------------|
| Sample Rate ($f_s$)| 16 kHz                        |
| Sample Size        | 16-bit Signed Little-Endian   |
| Format             | PCM                           |
| Channels           | 1 (Mono)                      |
| Transport          | UART (460,800 baud)           |
| Ring Buffer        | 4096 bytes                    |
| Filter Topology    | 1st-Order IIR / EMA ($\alpha = 0.28$, $f_c \approx 1\text{ kHz}$) |
| FFT Length ($N$)   | 128-Point Radix-2 (Hanning Windowed) |
| Bin Resolution ($\Delta f$) | 125 Hz / bin (64 positive bins, $0\text{–}8\text{ kHz}$) |
| Algorithmic Latency| ~8.5 – 9 ms (8 ms buffer + <0.5 ms compute @ 64 MHz) |

For mono 16-bit audio:

```text
16,000 samples/sec
× 2 bytes/sample
-----------------
32,000 bytes/sec
```

This makes the system suitable as a basic embedded audio acquisition pipeline.

## 🧩 Why Use the PC Sound Card as the ADC?

Traditional embedded microphone acquisition normally requires:

```text
Microphone
    │
    ▼
Analog Pre-Amplifier
    │
    ▼
Analog Filter
    │
    ▼
ADC
    │
    ▼
STM32
```

This project instead uses:

```text
Microphone
    │
    ▼
PC Sound Card / Audio ADC
    │
    ▼
Python
    │
    ▼
USB
    │
    ▼
UART
    │
    ▼
STM32
```

This approach allows the STM32 DSP pipeline to be developed without first designing a dedicated analog microphone front-end.

The PC therefore acts as the audio acquisition and ADC stage, while the STM32 becomes the embedded DSP processing platform.

## ⚠️ Important Limitations

This architecture is primarily intended as a development and prototyping bridge.

Because the audio originates from the PC:

- The PC is required during operation.
- The PC sound card determines the initial ADC characteristics.
- USB and UART introduce transport latency.
- The STM32 is not directly sampling the microphone's analog signal.
- The system is not yet a fully standalone embedded audio analyser.

A future standalone version can replace the PC audio acquisition stage with:

```text
Microphone
    │
    ▼
Analog Front-End
    │
    ▼
STM32 ADC / External Audio ADC
    │
    ▼
DSP
```

## 🔮 Next Steps / Roadmap

### Phase 1 — UART Byte Stream

- [x] Capture microphone audio on PC.
- [x] Convert audio into 16-bit PCM.
- [x] Stream audio over UART.
- [x] Implement interrupt-driven UART reception.
- [x] Implement 4096-byte ring buffer.
- [x] Implement UART error recovery.

### Phase 2 — PCM Reconstruction

- [x] Reconstruct the incoming 8-bit UART byte stream into 16-bit integers on the STM32.
- [x] Correctly handle little-endian sample ordering.
- [x] Verify reconstructed samples against the original Python samples.
- [x] Implement sample-level buffering (256-byte / 128-sample processing frames).

### Phase 3 — Digital Filtering

- [x] Implement an Exponential Moving Average (EMA) IIR Low-Pass Filter in C.
- [x] Remove high-frequency background noise ($f_c \approx 1\text{ kHz}$).
- [x] Calculate and tune smoothing coefficient ($\alpha = 0.28$).
- [x] Compare raw and filtered signals in frequency domain.
- [x] Measure processing latency (~8.5–9 ms total acoustic-to-spectrum delay).

### Phase 4 — Frequency-Domain Analysis (FFT)

- [x] Implement a 128-point Hanning window and in-place Radix-2 Cooley-Tukey FFT.
- [x] Perform real-time frequency analysis ($125\text{ Hz}$ resolution across 64 bins).
- [x] Generate $N/2$ normalized linear frequency-domain data (`fft_magnitudes`).
- [x] Identify dominant frequency components (`max_fft_observed`).
- [ ] Optional: Migrate custom C FFT to hardware-optimized CMSIS-DSP library.
- [ ] Investigate embedded spectrum visualization (OLED display or Python serial plotter).

### Phase 5 — Embedded Audio Analyser

The final objective is to evolve the bridge into a complete embedded audio analysis system:

```text
Microphone
    │
    ▼
Audio Acquisition
    │
    ▼
PCM Samples
    │
    ▼
STM32
    │
    ├── Ring Buffer
    │
    ├── Digital Filter
    │
    ├── FFT
    │
    └── Feature Extraction
            │
            ▼
      Audio Analysis
```

## 📌 Project Goal

The long-term goal of STM32-AudioAnalyser is to develop a complete embedded Digital Signal Processing pipeline capable of capturing, buffering, filtering, and analysing real-time audio signals on an STM32 microcontroller.

The current PC-to-UART architecture provides the initial hardware bridge required to develop and validate the DSP processing stages before moving toward a fully standalone microphone-to-STM32 implementation.
