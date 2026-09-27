# STM32-AudioAnalyser

A robust, real-time data pipeline that captures live microphone audio from a PC, converts it into a continuous 16-bit PCM stream, and transmits it via high-speed UART to an STM32 microcontroller.

This project serves as the foundational hardware bridge for embedded Digital Signal Processing (DSP). It bypasses the need for external analog pre-amplifier circuits by utilizing the PC's sound card as the ADC, funneling digitized, noise-free audio directly into the STM32's memory for real-time manipulation.

## 🚀 Current Features

- **Live Audio Capture:** Uses Python to grab real-time audio from any PC-connected microphone (analog or Bluetooth).
- **High-Speed Serial Streaming:** Transmits 16-bit PCM data over a Virtual COM Port at 460,800 baud.
- **Non-Blocking Architecture:** Thread-safe queueing on the Python host ensures the microphone never drops frames while waiting for USB serial writes.
- **Interrupt-Driven Ring Buffer:** The STM32 utilizes an asynchronous circular buffer (4096 bytes) to catch continuous audio data without halting the main CPU loop.
- **Bulletproof Error Recovery:** Custom hardware-level register resets prevent the STM32 from freezing during Overrun (ORE) or Framing errors caused by heavy interrupt loads.

## 🛠️ Tools & Hardware Required

### Hardware

- STM32 Nucleo-F103RB Development Board
- PC with an audio input device (Analog Mic / Headset / Earbuds)
- Mini-USB to USB-A cable (for ST-LINK programming and serial communication)

### Software

- **IDE:** [STM32CubeIDE](https://www.st.com/en/development-tools/stm32cubeide.html)
- **Environment:** Python 3.8+
- **Python Libraries:** `sounddevice`, `pyserial`, `numpy`

## 📂 Repository Structure

```text
nord-buds-stm32-bridge/
├── python_host/
│   ├── AudioBlue.py            # Main audio capture and UART streaming script
│   └── requirements.txt        # Python dependencies
├── stm32_firmware/
│   ├── Core/                   # Main C application code (main.c, ring buffer, callbacks)
│   ├── Drivers/                # STM32 HAL and CMSIS drivers
│   ├── AudioSignalAnalyser.ioc # STM32CubeMX configuration file
│   └── .project                # STM32CubeIDE project files
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
8. Click **Run/Debug** using the Green Play Button to flash the firmware onto the STM32.

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
5. Install the required Python dependencies:
   ```bash
   pip install -r requirements.txt
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
Future DSP Processing
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

The STM32 uses a 4096-byte circular/ring buffer to decouple UART reception from future DSP processing.

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

| Parameter   | Value      |
|-------------|------------|
| Sample Rate | 16 kHz     |
| Sample Size | 16-bit     |
| Format      | PCM        |
| Channels    | Depends on host configuration |
| Transport   | UART       |
| Baud Rate   | 460800 baud |
| Buffer      | 4096 bytes |

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

- [ ] Reconstruct the incoming 8-bit UART byte stream into 16-bit integers on the STM32.
- [ ] Correctly handle little-endian sample ordering.
- [ ] Verify reconstructed samples against the original Python samples.
- [ ] Implement sample-level buffering.

### Phase 3 — Digital Filtering

- [ ] Implement an Exponential Moving Average (EMA) IIR Low-Pass Filter in C.
- [ ] Remove high-frequency background noise.
- [ ] Experiment with different smoothing coefficients.
- [ ] Compare raw and filtered signals.
- [ ] Measure processing latency.

### Phase 4 — CMSIS-DSP Integration

- [ ] Integrate the CMSIS-DSP library.
- [ ] Implement an FFT.
- [ ] Perform real-time frequency analysis.
- [ ] Generate frequency-domain data.
- [ ] Identify dominant frequency components.
- [ ] Investigate embedded spectrum visualization.

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
