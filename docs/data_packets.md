# Packet Format
All packets are recieved as raw ethernet frames with a protocol set as type 0x88b5 which wireshark identifies as 'Local Experimental Ethertype 1'

Following the ethernet header, various types of data packets can be seen from coming from the device. 

## Header
All packets start with a 30 byte long header formatted as below

| Start Address | Size (Bytes) | Description        | Contents            |
|---------------|--------------|--------------------|---------------------|
|      0x00     |       4      | Packet Header?     | CB DA E9 F8         |
|      0x04     |      16      | Unknown (Padding?) | 0x00                |
|      0x14     |       1      | Unknown            | 0x01                |
|      0x15     |       3      | Unknown (Padding)  | 0x00                |
|      0x18     |       1      | Message Length     | Various (See Below) |
|      0x19     |       1      | Network ID         | Shown on the device as Information 3/6 "Network ID" (e.g. 169 = 0xA9); 0x53 and 0xE5 seen on other networks |
|      0x1A     |       2      | Message Type  1  ? |                     |
|      0x1B     |       2      | Message Type  2  ? |                     |
|      0x1C     |       1      | Device type        | 0xC8 = Eddi, 0xD0 = Zappi. Frames of the same packet type are laid out differently per device. 0x81 is seen with serial "Zappi + 1" (e.g. 20713857), not yet identified |

## Where the frames come from
myenergi devices talk to each other over an 868 MHz radio link. An Eddi V2.1 also copies every radio packet it **transmits** out over Wi-Fi as these raw frames (its "Packet Counters" screen shows Radio Tx and WiFi Tx counting in step, at about 1.4 packets per second). Packets it **receives** by radio are not copied. So with an Eddi alone on the network you only see the Eddi's own data: for example, when the grid CT is wired to a Zappi ("Grid Sensor: Remote"), the live grid readings stay on the radio link and no `0x22` CT packets appear.

Once the Zappi is on Wi-Fi it sends its own frames to the same multicast group, from its own MAC. These include the grid CT readings (`0x2A`, below). The Zappi's "MElink Packets" WiFi Tx counter matched the number of frames captured from it.

## Common fields
These fields sit at the same offsets in every packet type observed from an Eddi V2.1 except `0x36` (on a Zappi only the serial and frequency are known to match, plus voltage at 0x32 in `0x1F`):

| Start Address | Size (Bytes) | Data Type | Description | Post Processing |
|---------------|--------------|-----------|-------------|-----------------|
|      0x1E     |       4      |  uint32   | Serial Number | N/A |
|      0x22     |       2      |  uint16   | Frequency | / 100 |
|      0x25     |       1      |  bits     | Status (bit 7: stopped) | |
|      0x26     |       2      |  uint16   | Heater max power (W), "MaxPower" on the Eddi's diagnostic screens. While the heater runs it is the measured element power (2.88 kW on a 3 kW element); when idle a nominal value that tracks V² / 15 Ω, i.e. 16 A (≈3.84 kW at 240 V) | N/A |
|      0x2C     |       2      |  uint16   | Diverted energy today (kWh). Surplus diversion only: does **not** count boost (stayed at 0.00 through a 4 minute, 2.86 kW boost) | / 100 |
|      0x2E     |       1      |  bits     | Status (bit 4: boost) | |
|      0x2F     |       1      |  bits     | Selected heater (bit 0: heater 1, bit 1: heater 2) | |

Various Types of packets have been observed so far. 
## Packet Types

| Packet Len  | Data Length (Bytes) | Contents                        | Transmit Rate (Seconds) |  Notes                       |
|-------------|---------------------|---------------------------------|-------------------------|------------------------------|
|     0x1F    |          55         | Eddi Data (Packet Type 1)       |            24           |                              |
|     0x20    |          56         | Eddi Data (Packet Type 2)       |            12           |                              |
|     0x2B    |          67         | Eddi Data (Packet Type 3)       |            12           | data not consistant          |
|     0x2C    |          68         | ??                              |            12           |                              |
|     0x2D    |          69         | ??                              |            12           |                              |
|     0x22    |          58         | CT Readings?                    |            2            |                              |
|     0x2A    |          66         | Zappi CT readings               |            1            | Zappi only                   |
|     0x33    |          75         | Zappi per-CT readings           |            5            | Zappi only                   |
|     0x3E    |          86         | Zappi per-minute history record |            2            | Zappi only, replays history  |
|     0x27    |          63         | Unknown                         |            4            |                              |
|     0x36    |          78         | Per-minute history record       |            2            | replays ~a week of records   |
|     0x37    |          79         | Unknown                         |            tbc          |                              |
|     0x38    |          80         | Unknown                         |            tbc          |                              |
|     0x39    |          81         | Unknown                         |            tbc          |                              |
|     0x3a    |          82         | Unknown                         |            tbc          |                              |

The following Packets have been decoded (or partially decoded) so far

### 0x1F - Eddi Data (Packet Type 1)

Transmitted Approx Every 12 seconds

| Start Address | Size (Bytes) | Data Type | Description    | Post Processing |
|---------------|--------------|-----------|----------------|-----------------|
|      0x1E     |       4      |   int32   | Serial Number  | N/A             |
|      0x22     |       2      |   int16   | Grid Frequency | Divide by 100   |
|      0x2C     |       2      |   int16   | Diverted kWh   |   / 100         |
|      0x32     |       2      |   int16   | Voltage        | Divide by 10    |

###  0x20 - Eddi Data (Packet Type 2)

Transmitted Approx Every 24 seconds

| Start Address | Size (Bytes) | Data Type | Description          | Post Processing |
|---------------|--------------|-----------|----------------------|-----------------|
|      0x1E     |       4      |   int32   | Serial Number        | N/A             |
|      0x22     |       2      |   int16   | Grid Frequency       | Divide by 100   |
|      0x2C     |       2      |   int16   | Diverted kWh         |   / 100         |
|      0x24     |       2      |   bool    | Status Bit?          |                 |
|      0x26     |       2      |   int16   | Max Heater Power (*1)|                 |
|      0x34     |       2      |   int16   | Divert Power (W)     | N/A (matches the Eddi display) |
|      0x36     |       2      |   int16   | Heater current (A); 12.2 A at 2.86 kW / 235 V. Reads 0.01-0.50 when idle | / 100 |
|      0x2E (mask 0x10) | 1  | bool      | Boosting (confirmed with a manual boost) |  N/A            |
|      0x2F.7   |       1      | bool      | Heater 1 Active      |  N/A            |
|      0x2F.6   |       1      | bool      | Heater 2 Active      |  N/A            |
|      0x2F.5   |       1      | bool      | unknown              |  N/A            |
|      0x2F.4   |       1      | bool      | unknown              |  N/A            |
|      0x2F.3   |       1      | bool      | unknown              |  N/A            |
|      0x2F.2   |       1      | bool      | unknown              |  N/A            |
|      0x2F.1   |       1      | bool      | unknown              |  N/A            |
|      0x2F.0   |       1      | bool      | unknown              |  N/A            |
|      0x25.7   |       1      | bool      | Stopped Mode         |  N/A            |


1. Appears to be the maximum heater power that is connected to the active channel. For example, if you had a 3kW heater then this would read 3000. Sits at maximum rated power (3600) when nothing is connected or channel is off. 

### 0x2B - Eddi Data (Packet Type 3)

Transmitted approx ever 12 seconds. Occasionally sends odd vales for generation & grid power

| Start Address | Size (Bytes) | Data Type | Description                                             | Post Processing |
|---------------|--------------|-----------|---------------------------------------------------------|-----------------|
|      0x1E     |       4      |   int32   | Serial Number                                           | N/A             |
|      0x22     |       2      |   int16   | Frequency                                               | Divide by 100   |
|      0x2C     |       2      |   int16   | Diverted kwH                                            | Divide by 100   | 
|      0x3C     |       2      |   int16   | Generation Power                                        |                 |
|      0x34     |       2      |   int16   | Grid Power                                              |                 |


### 0x22 - CT Readings?

Transmitted Approx ever 2 seconds

| Start Address | Size (Bytes) | Data Type | Description      | Post Processing |
|---------------|--------------|-----------|------------------|-----------------|
|      0x1E     | 2            |   int16   | Grid Power       | N/A             |
|      0x22     | 2            |   int16   | Generation Power | N/A             |
|      0x32     | 2            |   int16   | Diverting Power  | N/A             |
|      0x2E     | 4            |   int32   | Serial Number    | N/A             |


### 0x2A - Zappi CT readings

Sent by a Zappi about once a second: the CT readings it sends the Eddi over the radio so the Eddi can divert. The same fields as `0x22`, but 32 bits wide and with the serial one byte later. Checked against the Zappi's "Importing" screen (it lags the frames by about a second).

| Start Address | Size (Bytes) | Data Type | Description | Post Processing |
|---------------|--------------|-----------|-------------|-----------------|
|      0x1E     |       4      |   int32   | Grid power (W), positive = import | N/A |
|      0x22     |       4      |   int32   | Generation power (W)? 0 here, no generation CT fitted | N/A |
|      0x26     |       4      |   int32   | Unknown, noisy | |
|      0x2D     |       4      |  uint32   | Eddi serial number | N/A |
|      0x31     |       2      |   int16   | Eddi power as seen by the Zappi (W), tracks the Eddi's own `0x20` divert power | N/A |
|      0x34     |       4      |  uint32   | Zappi serial number | N/A |
|      0x3B     |       4      |  uint32   | Zappi serial + 1 | N/A |

### 0x33 - Zappi per-CT readings

Sent by a Zappi about every 5 seconds. Serial at 0x1E as usual; from 0x30 one 8-byte block per external CT (CT2 to CT4 here; CT1, the Zappi's internal EV CT, is not included):

| Offset in block | Size (Bytes) | Data Type | Description |
|---|---|---|---|
| 0 | 1 | uint8 | 0x08 |
| 1 | 1 | uint8 | CT number in the high nibble (0x21 = CT2) |
| 2 | 1 | uint8 | CT type, as in the "TY" column of the Zappi's CT screens: 0 none, 1 grid, 4 seen on a home battery / inverter |
| 3 | 1 | uint8 | 0 |
| 4 | 2 | int16 | Power (W). For the grid CT positive = import; matches `0x2A` within ~10 W |
| 6 | 2 | uint16 | Current (/ 100 A). e.g. 4.31 A at 1033 W and 241 V |

On a sunny day the type 4 CT supplied the house (keeping grid import near zero) until 17:41, then dropped from about 1 kW to 0 in one step, the way a battery reaching its floor does.

### 0x3E - Zappi per-minute history record (partial)

Like the Eddi's `0x36`: starts with `5A 5A`, has 60 at 0x26 (seconds in the record), and the Zappi replays its stored records the same way (on first connect, records from six days earlier, one every 2 seconds). The date at 0x21-0x24 matches the Eddi's encoding; the minute is in the low 6 bits of 0x20 and the month in the low 4 bits of 0x23. Fields (checked against the Eddi's `0x36` over 4,761 shared minutes and the live `0x33` readings): 0x38 grid export (W, matches the Eddi's 0x34 within 2 W), 0x3A grid import (W, matches the Eddi's 0x36), 0x3C/0x3E/0x40 voltage of phases 1-3 (/ 10), 0x42 frequency (/ 100), 0x44 unit temperature (/ 10, matches the Zappi's "Unit Temp"), 0x46 a second import reading (within a few W of 0x3A), 0x48 CT3 power (W, matches `0x33`), serial at 0x52. Not decoded by the bridge yet.

### 0x27 - Unknown

Transmitted approx every 4 seconds

| Start Address | Size (Bytes) | Data Type | Description                                             | Post Processing |
|---------------|--------------|-----------|---------------------------------------------------------|-----------------|
|      0x1E     |       4      |   int32   | Serial Number                                           | N/A             |
|      0x22     |       2      |   int16   | Grid Frequency                                          | Divide by 100   |
|      0x2C     |       2      |   int16   | Diverted kWh                                            |   / 100         |
|      0x36     |       2      |   int16   | Firmware Version (But appears to occasionally go blank) |                 | 
|      0x38     |       2      |   int16   | Firmware Version2(But appears to occasionally go blank) |                 |
|      0x3A     |       2      |   int16   | Unknown                                                 |                 | 
|      0x3D     |       2      |   int16   | Unknown. Seems to track diverter power but not exactly  |                 |


### 0x36 - Per-minute history record

Transmitted approx every 2 seconds. Each frame carries one stored record of one-minute averages. The Eddi keeps sending its stored records (about a week of them) mixed in with the record for the minute that just ended. That record first arrives about 2 minutes after its minute starts and is repeated several times. A record is only "live" if it is newer than every record seen before.

Values confirmed against the Eddi's readings screens on an Eddi V2.1.

| Start Address | Size (Bytes) | Data Type | Description                                             | Post Processing |
|---------------|--------------|-----------|---------------------------------------------------------|-----------------|
|      0x1A     |       4      |           | Constant `5A 5A C8 01`                                  |                 |
|      0x1E     |       2      |           | Constant `30 0C` (0 in an all-zero record)              |                 |
|      0x20     |       1      |   uint8   | Record time: minute                                     |                 |
|      0x21     |       1      |   uint8   | Record time: hour (bits 0-4), weekday (bits 5-7, Monday = 0) | `& 0x1F` / `>> 5` |
|      0x22     |       1      |   uint8   | Record date: day                                        |                 |
|      0x23     |       1      |   uint8   | Record date: month                                      |                 |
|      0x24     |       1      |   uint8   | Record date: year                                       | + 2000          |
|      0x26     |       1      |   uint8   | Seconds in the record (59 or 60)?                       |                 |
|      0x28     |       2      |   int16   | Heater power from diversion (W), one-minute average. Matches the live divert power within 2%; summed, it tracks the Eddi's diverted kWh | N/A |
|      0x2A     |       2      |   int16   | Usually zero; another channel (generation?)             |                 |
|      0x2C     |       2      |   int16   | Heater power from boost (W), one-minute average. 0 while diverting | N/A |
|      0x2E     |       6      |   int16   | Usually zero; other channels?                           |                 |
|      0x34     |       2      |   int16   | Grid export (W), one-minute average: 4-64 W while the Eddi diverts to keep the grid near zero, 0 at night. Matches the Zappi's own history record within 2 W | N/A |
|      0x36     |       2      |   int16   | Grid import (W), one-minute average. Import and export are averaged separately, so this never goes negative | N/A |
|      0x38     |       2      |   int16   | Voltage                                                 | / 10            |
|      0x3A     |       2      |   int16   | Frequency                                               | / 100           |
|      0x3C     |       2      |   int16   | Heatsink temperature (°C)                               | / 10            |
|      0x4A     |       4      |   int32   | Serial Number                                           | N/A             |

The record time is the Eddi's local time (as set on the device). The Eddi's clock may drift from real time; one unit ran about 65 seconds behind. The minimum/maximum voltage and grid current shown on the Eddi's readings screens were not found in any packet.

### 0x37 - Device information

Constant apart from the common fields.

| Start Address | Size (Bytes) | Data Type | Description                                             | Post Processing |
|---------------|--------------|-----------|---------------------------------------------------------|-----------------|
|      0x1E     |       4      |   int32   | Serial Number                                           | N/A             |
|      0x30     |       6      |           | Unknown identifier (not the Eddi's MAC or EUI)          |                 |
|      0x3C     |       6      |  uint16   | Unknown constants (1244, 1036, 1444 at 0x3C/0x3E/0x40) |                 |
|      0x42     |       2      |  uint16   | Firmware version (5435 = V5.435)                        | major = v / 1000, minor = v % 1000 |
|      0x44     |       2      |  uint16   | Unknown constant (3202)                                 |                 |
|      0x46     |       2      |  uint16   | melib version (1303 for v4.1.303)                       |                 |
|      0x48     |       2      |  uint16   | Unknown constant (228)                                  |                 |
