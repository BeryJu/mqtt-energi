import datetime
import struct

from modules import log

logger = log.get("decoder")

# Per-serial state for 0x36 history records: (frames seen, newest record time)
_history = {}
# Packet types without a decoder, so each is only logged once
_unknown_types = set()
# Per-serial heater energy (kWh) summed from the 0x36 minute records since the
# bridge started. Published as a total_increasing counter: Home Assistant treats
# the drop to 0 after a restart as a new cycle, so nothing is lost or doubled.
_heater_energy = {}
# Devices on one network are told apart by header byte 0x1C. Frames of the same
# packet type are laid out differently on each, so only decode what is known.
EDDI = 0xC8
ZAPPI = 0xD0
DEVICE_MODELS = {EDDI: "Eddi", ZAPPI: "Zappi"}
# Device bytes without a decoder, so each is only logged once
_unknown_devices = set()
# Replayed records are never newer than the current one. After this many 0x36
# frames (about a minute) the newest record seen is the live one.
HISTORY_WARMUP_FRAMES = 30


def _history_time(eth_pkt):
    """Record time from a 0x36 frame, in the Eddi's local time (naive)."""
    try:
        return datetime.datetime(
            2000 + eth_pkt[0x24],  # year
            eth_pkt[0x23],  # month
            eth_pkt[0x22],  # day
            eth_pkt[0x21] & 0x1F,  # hour (top 3 bits: weekday, Monday = 0)
            eth_pkt[0x20],  # minute
        )
    except ValueError:  # all-zero / malformed record
        return None


def _history_is_new(serial, record_time):
    seen, newest = _history.get(serial, (0, None))
    is_newer = newest is None or record_time > newest
    _history[serial] = (seen + 1, record_time if is_newer else newest)
    if seen + 1 == HISTORY_WARMUP_FRAMES:
        logger.info(
            "history warm-up done",
            serial=serial,
            newest_record=(record_time if is_newer else newest).isoformat(),
        )
    return is_newer and seen + 1 >= HISTORY_WARMUP_FRAMES


def status_decode(inbyte):
    return [1 if inbyte & (1 << (7 - n)) else 0 for n in range(8)]


def device_model(eth_pkt):
    """Model name of the sending device ("Eddi", "Zappi"), or None if unknown."""
    return DEVICE_MODELS.get(eth_pkt[0x1C])


def _log_unknown_type(eth_pkt):
    packet_type = eth_pkt[0x18]
    if (eth_pkt[0x1C], packet_type) not in _unknown_types:
        _unknown_types.add((eth_pkt[0x1C], packet_type))
        logger.info(
            "unknown packet type (logged once per type)",
            device=f"0x{eth_pkt[0x1C]:02X}",
            packet_type=f"0x{packet_type:02X}",
            length=len(eth_pkt),
            payload=eth_pkt.hex(),
        )


def decode_zappi(eth_pkt, debug):
    packet_type = eth_pkt[0x18]
    data = {}
    if packet_type == 0x1F:  # Same voltage/frequency fields as the Eddi's
        data = {
            "serial": int.from_bytes(eth_pkt[0x1E:0x22], "little"),
            "frequency": int.from_bytes(eth_pkt[0x22:0x24], "little") / 100,
            "voltage": int.from_bytes(eth_pkt[0x32:0x34], "little") / 10,
        }
    elif packet_type == 0x2A:  # CT readings, about once a second
        # The grid CT reading the Zappi sends to the Eddi so it can divert. Laid out
        # like 0x22, but with 32-bit values and the serial one byte later.
        grid_pwr = int.from_bytes(eth_pkt[0x1E:0x22], "little", signed=True)
        data = {
            "serial": int.from_bytes(eth_pkt[0x34:0x38], "little"),
            "grid_pwr_w": grid_pwr,
        }
        if debug:
            # Generation CT (none fitted here, always 0) and the Eddi's power
            # as the Zappi sees it
            data["0x2A/gen_pwr_w"] = int.from_bytes(
                eth_pkt[0x22:0x26], "little", signed=True
            )
            data["0x2A/eddi_serial"] = int.from_bytes(eth_pkt[0x2D:0x31], "little")
            data["0x2A/eddi_pwr_w"] = int.from_bytes(
                eth_pkt[0x31:0x33], "little", signed=True
            )
    else:
        # Per-minute history (0x3E) and the rest are not mapped yet
        _log_unknown_type(eth_pkt)
    return data


def decode_packet(eth_pkt, debug):
    device = eth_pkt[0x1C]
    packet_type = eth_pkt[0x18]
    if device == ZAPPI:
        return decode_zappi(eth_pkt, debug)
    if device != EDDI and packet_type != 0x22:
        if device not in _unknown_devices:
            _unknown_devices.add(device)
            logger.info(
                "frames from an unknown device type are ignored (logged once)",
                device=f"0x{device:02X}",
                packet_type=f"0x{packet_type:02X}",
                payload=eth_pkt.hex(),
            )
        return {}
    data = {}

    if packet_type == 0x1F:  # Frequency Message
        serialno = int.from_bytes(eth_pkt[0x1E:0x22], "little")
        freq = int.from_bytes(eth_pkt[0x22:0x24], "little")
        div_wh = int.from_bytes(eth_pkt[0x2C:0x2E], "little")
        voltage = int.from_bytes(eth_pkt[0x32:0x34], "little")
        data = {
            "serial": serialno,
            "frequency": freq / 100,
            "voltage": voltage / 10,
            "diverted_kWh": div_wh / 100,
        }

    elif packet_type == 0x20:  # Diverter Data?
        serialno = int.from_bytes(eth_pkt[0x1E:0x22], "little")
        div_wh = int.from_bytes(eth_pkt[0x2C:0x2E], "little")
        divert_pwr = int.from_bytes(eth_pkt[0x34:0x36], "little")
        divert_cur = int.from_bytes(eth_pkt[0x36:0x38], "little")  # not sure about this
        # Power the heater would draw at full output (V^2 / element resistance)
        max_power = int.from_bytes(eth_pkt[0x26:0x28], "little")
        status = status_decode(int(eth_pkt[0x2F]))
        status2 = status_decode(int(eth_pkt[0x25]))
        status3 = status_decode(int(eth_pkt[0x2E]))
        heater1 = status[7]
        heater2 = status[6]
        boost = status3[3]
        stopped = status2[0]

        data = {
            "serial": serialno,
            "diverted_kWh": div_wh / 100,
            "divert_pwr_w": divert_pwr,
            #'divert_cur':divert_cur,
            "heater1": heater1,
            "heater2": heater2,
            "stopped": stopped,
            "boost": boost,
            "heater_max_pwr_w": max_power,
        }
    elif packet_type == 0x2B:  # Data ?
        serialno = int.from_bytes(eth_pkt[0x1E:0x22], "little")
        freq = int.from_bytes(eth_pkt[0x22:0x24], "little")
        div_wh = int.from_bytes(eth_pkt[0x2C:0x2E], "little")
        gen_pow = int.from_bytes(
            eth_pkt[0x3C:0x3E], "little", signed=True
        )  # occasionally goes zero
        grid_pow = int.from_bytes(
            eth_pkt[0x34:0x36], "little", signed=True
        )  # occasionally goes to weird value
        div_pow = int.from_bytes(eth_pkt[0x41:0x43], "little", signed=True)
        v1 = int.from_bytes(
            eth_pkt[0x41:0x43], "little", signed=True
        )  # proportional to generation
        if debug:
            data = {
                "serial": serialno,
                "frequency": freq / 100,
                "diverted_kWh": div_wh / 100,
                #'gen_pwr':gen_pow,
                #'grid_pwr':grid_pow,
                "divert_pwr_w": div_pow,
            }

    elif packet_type == 0x22:  # CT Readings
        gen_pow = int.from_bytes(
            eth_pkt[0x22:0x24], "little", signed=True
        )  # Generation Power
        grid_pow = int.from_bytes(
            eth_pkt[0x1E:0x20], "little", signed=True
        )  # Grid Power
        div_pow = int.from_bytes(
            eth_pkt[0x32:0x34], "little", signed=True
        )  # Diverter Power
        serialno = int.from_bytes(eth_pkt[0x2E:0x32], "little")  # Serial No
        data = {
            "serial": serialno,
            "gen_pwr": gen_pow,
            "grid_pwr": grid_pow,
            "divert_pwr_w": div_pow,
        }

    elif packet_type == 0x27:  # Data ?
        serialno = int.from_bytes(eth_pkt[0x1E:0x22], "little")
        freq = int.from_bytes(eth_pkt[0x22:0x24], "little")
        div_wh = int.from_bytes(eth_pkt[0x2C:0x2E], "little")
        fw1 = int.from_bytes(eth_pkt[0x38:0x3A], "little", signed=True)
        fw2 = int.from_bytes(eth_pkt[0x36:0x38], "little", signed=True)
        v1 = int.from_bytes(
            eth_pkt[0x3D:0x3E], "little", signed=True
        )  # seems to track diverter power but not exactly. possibly output voltage?
        v2 = int.from_bytes(eth_pkt[0x3C:0x3D], "little", signed=True)
        v3 = int.from_bytes(eth_pkt[0x3A:0x3C], "little", signed=True)
        v4 = int.from_bytes(eth_pkt[0x34:0x36], "little", signed=True)
        v5 = int.from_bytes(eth_pkt[0x32:0x34], "little", signed=True)
        v6 = int.from_bytes(eth_pkt[0x30:0x32], "little", signed=True)
        v7 = int.from_bytes(eth_pkt[0x2E:0x30], "little", signed=True)
        if debug:
            data = {
                "serial": serialno,
                "frequency": freq / 100,
                "diverted_kWh": div_wh / 100,
                "0x27/fw1": fw1,
                "0x27/fw2": fw2,
                "0x27/v1": v1,
                "0x27/v2": v2,
                "0x27/v3": v3,
                "0x27/v4": v4,
                "0x27/V5": v5,
                "0x27/v6": v6,
                "0x27/v7": v7,
            }

    elif packet_type == 0x37:  # Device info (constant)
        serialno = int.from_bytes(eth_pkt[0x1E:0x22], "little")
        firmware = int.from_bytes(eth_pkt[0x42:0x44], "little")  # 5435 = V5.435
        data = {
            "serial": serialno,
            "firmware": f"{firmware // 1000}.{firmware % 1000:03d}",
        }
        if debug:
            # 1303 for melib v4.1.303
            data["0x37/melib"] = int.from_bytes(eth_pkt[0x46:0x48], "little")
            data["0x37/id"] = eth_pkt[0x30:0x36].hex()
            for off in (0x3C, 0x3E, 0x40, 0x44, 0x48):  # constant, unknown
                data[f"0x37/raw_{off:02x}"] = int.from_bytes(
                    eth_pkt[off : off + 2], "little"
                )

    elif packet_type == 0x36:  # Per-minute history record
        # The Eddi keeps sending its stored one-minute records (about a week of
        # them), mixed in with the record for the minute that just ended. Only
        # publish records newer than any seen before; see _history_is_new().
        serialno = int.from_bytes(eth_pkt[0x4A:0x4E], "little")
        record_time = _history_time(eth_pkt)
        if record_time is not None and _history_is_new(serialno, record_time):
            # The heater's power is logged by source: surplus solar diverted to
            # it, and grid power during boost.
            diverted_pwr = int.from_bytes(eth_pkt[0x28:0x2A], "little", signed=True)
            boost_pwr = int.from_bytes(eth_pkt[0x2C:0x2E], "little", signed=True)
            heater_pwr = max(diverted_pwr, 0) + max(boost_pwr, 0)
            # Import and export are averaged separately (not one net value)
            grid_import = int.from_bytes(eth_pkt[0x36:0x38], "little", signed=True)
            grid_export = int.from_bytes(eth_pkt[0x34:0x36], "little", signed=True)
            voltage = int.from_bytes(eth_pkt[0x38:0x3A], "little")
            freq = int.from_bytes(eth_pkt[0x3A:0x3C], "little")
            heatsink = int.from_bytes(eth_pkt[0x3C:0x3E], "little", signed=True)
            # Seconds covered by the record (59 or 60)
            seconds = eth_pkt[0x26] if 0 < eth_pkt[0x26] <= 60 else 60
            # Diverted and boost heating (diverted_kWh leaves out boost)
            energy = _heater_energy.get(serialno, 0.0)
            energy += heater_pwr * seconds / 3_600_000
            _heater_energy[serialno] = energy
            data = {
                "serial": serialno,
                "heater_pwr_1m_w": heater_pwr,
                "heater_kWh": round(energy, 4),
                "grid_pwr_1m_w": grid_import,
                "heatsink_temp_c": heatsink / 10,
            }
            if debug:
                data["0x36/record_time"] = record_time.isoformat()
                data["0x36/samples"] = eth_pkt[0x26]
                data["0x36/voltage_1m"] = voltage / 10
                data["0x36/frequency_1m"] = freq / 100
                data["0x36/heater_diverted_w"] = diverted_pwr
                data["0x36/heater_boost_w"] = boost_pwr
                # Very likely export; not yet confirmed
                data["0x36/grid_export_w"] = grid_export
                # Usually zero; other channels (generation?) not yet mapped
                for off in (0x2A, 0x2E, 0x30, 0x32):
                    data[f"0x36/raw_{off:02x}"] = int.from_bytes(
                        eth_pkt[off : off + 2], "little", signed=True
                    )
    elif packet_type == 0x38:  # ?
        serialno = int.from_bytes(eth_pkt[0x1E:0x22], "little")
        v1 = int.from_bytes(eth_pkt[0x20:0x22], "little", signed=True)
        v2 = int.from_bytes(eth_pkt[0x22:0x24], "little", signed=True)
        v3 = int.from_bytes(eth_pkt[0x24:0x26], "little", signed=True)  # Frequency
        v4 = int.from_bytes(eth_pkt[0x26:0x28], "little", signed=True)  # Voltage?
        v5 = int.from_bytes(eth_pkt[0x28:0x2A], "little", signed=True)
        v6 = int.from_bytes(eth_pkt[0x2A:0x2C], "little", signed=True)
        v7 = int.from_bytes(eth_pkt[0x2C:0x2E], "little", signed=True)
        v8 = int.from_bytes(eth_pkt[0x2E:0x30], "little", signed=True)
        v9 = int.from_bytes(eth_pkt[0x30:0x32], "little", signed=True)
        v10 = int.from_bytes(eth_pkt[0x32:0x34], "little", signed=True)
        v11 = int.from_bytes(eth_pkt[0x34:0x36], "little", signed=True)
        v12 = int.from_bytes(eth_pkt[0x36:0x38], "little", signed=True)
        v13 = int.from_bytes(eth_pkt[0x38:0x3A], "little", signed=True)
        v14 = int.from_bytes(eth_pkt[0x3A:0x3C], "little", signed=True)
        v15 = int.from_bytes(eth_pkt[0x3C:0x3E], "little", signed=True)
        v16 = int.from_bytes(eth_pkt[0x3E:0x40], "little", signed=True)
        if debug:
            data = {
                "serial": serialno,
                "0x38/v1": v1,
                "0x38/v2": v2,
                "0x38/v3": v3,
                "0x38/v4": v4,
                "0x38/v5": v5,
                "0x38/v6": v6,
                "0x38/v7": v7,
                "0x38/v8": v8,
                "0x38/v9": v9,
                "0x38/v10": v10,
                "0x38/v11": v11,
                "0x38/v12": v12,
                "0x38/v13": v13,
                "0x38/v14": v14,
                "0x38/v15": v15,
                "0x38/v16": v16,
            }

    elif packet_type == 0x3A:  # ?
        serialno = int.from_bytes(eth_pkt[0x1E:0x22], "little")
        v2 = int.from_bytes(eth_pkt[0x22:0x24], "little", signed=True)
        v3 = int.from_bytes(eth_pkt[0x24:0x26], "little", signed=True)
        v4 = int.from_bytes(eth_pkt[0x26:0x28], "little", signed=True)
        v5 = int.from_bytes(eth_pkt[0x28:0x2A], "little", signed=True)
        v6 = int.from_bytes(eth_pkt[0x2A:0x2C], "little", signed=True)
        v7 = int.from_bytes(eth_pkt[0x2C:0x2E], "little", signed=True)
        v8 = int.from_bytes(eth_pkt[0x2E:0x30], "little", signed=True)
        v9 = int.from_bytes(eth_pkt[0x30:0x32], "little", signed=True)
        v10 = int.from_bytes(eth_pkt[0x32:0x34], "little", signed=True)
        v11 = int.from_bytes(eth_pkt[0x34:0x36], "little", signed=True)
        v12 = int.from_bytes(eth_pkt[0x36:0x38], "little", signed=True)
        v13 = int.from_bytes(eth_pkt[0x38:0x3A], "little", signed=True)
        v14 = int.from_bytes(eth_pkt[0x44:0x46], "little", signed=True)
        v15 = int.from_bytes(eth_pkt[0x42:0x44], "little", signed=True)
        if debug:
            data = {
                "serial": serialno,
                "0x3A/v2": v2,
                "0x3A/v3": v3,
                "0x3A/v4": v4,
                "0x3A/v5": v5,
                "0x3A/v6": v6,
                "0x3A/v7": v7,
                "0x3A/v8": v8,
                "0x3A/v9": v9,
                "0x3A/v10": v10,
                "0x3A/v11": v11,
                "0x3A/v12": v12,
                "0x3A/v13": v13,
                "0x3A/v14": v14,
                "0x3A/v15": v15,
            }

    else:
        _log_unknown_type(eth_pkt)
    return data
