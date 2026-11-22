# BLE HID keyboard for TVAutoPilot.
#
# The TV pairs to this board. The board does not connect out to the TV.
# Pairing is Just Works with bonding and no PIN: a television cannot type
# a passkey. The report map runs through F24 (usage 0x73). A map that
# stops at usage 0x65 makes a strict TV drop F13.
#
# VID/PID bytes match the Arduino BLEHIDDevice layout this project was
# paired as (USB vendor source, Apple 0x05AC / 0x820A / version 0x0210,
# 16-bit fields stored high byte first, as that library writes them).
# A different id is more likely to make a set ignore the keyboard.
#
# Bonds are written to bonds.txt. The NimBLE stack asks for them through
# the BLE irq; they are not kept for us across a reboot.

try:
    from micropython import const
except ImportError:
    def const(x):
        return x

try:
    import bluetooth
except ImportError:
    bluetooth = None

import binascii
import time

_FLAG_READ = const(0x0002)
_FLAG_WRITE_NO_RESPONSE = const(0x0004)
_FLAG_WRITE = const(0x0008)
_FLAG_NOTIFY = const(0x0010)

_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_ENCRYPTION_UPDATE = const(28)
_IRQ_GET_SECRET = const(29)
_IRQ_SET_SECRET = const(30)
_IRQ_PASSKEY_ACTION = const(31)

_IO_CAPABILITY_NO_INPUT_OUTPUT = const(3)
_PASSKEY_ACTION_NUMERIC_COMPARISON = const(4)

# 30 ms. The stack rounds this down to a multiple of 625 us.
_ADV_INTERVAL_US = const(30000)

_APPEARANCE_KEYBOARD = const(0x03C1)
_HID_SERVICE = const(0x1812)

# Keyboard collection only. Usage maximum 0x73 is F24, so F13 (0x68) is legal.
# Same item layout as the vendored Arduino map, without the unused media page.
_REPORT_MAP = bytes((
    0x05, 0x01,  # Usage Page (Generic Desktop)
    0x09, 0x06,  # Usage (Keyboard)
    0xA1, 0x01,  # Collection (Application)
    0x85, 0x01,  #   Report ID (1)
    0x05, 0x07,  #   Usage Page (Key Codes)
    0x19, 0xE0,  #   Usage Minimum (224)
    0x29, 0xE7,  #   Usage Maximum (231)
    0x15, 0x00,  #   Logical Minimum (0)
    0x25, 0x01,  #   Logical Maximum (1)
    0x75, 0x01,  #   Report Size (1)
    0x95, 0x08,  #   Report Count (8)
    0x81, 0x02,  #   Input (Data, Var, Abs)        modifiers
    0x95, 0x01,  #   Report Count (1)
    0x75, 0x08,  #   Report Size (8)
    0x81, 0x01,  #   Input (Const)                 reserved
    0x95, 0x05,  #   Report Count (5)
    0x75, 0x01,  #   Report Size (1)
    0x05, 0x08,  #   Usage Page (LEDs)
    0x19, 0x01,  #   Usage Minimum (1)
    0x29, 0x05,  #   Usage Maximum (5)
    0x91, 0x02,  #   Output (Data, Var, Abs)       LED report
    0x95, 0x01,  #   Report Count (1)
    0x75, 0x03,  #   Report Size (3)
    0x91, 0x01,  #   Output (Const)                LED padding
    0x95, 0x06,  #   Report Count (6)
    0x75, 0x08,  #   Report Size (8)
    0x15, 0x00,  #   Logical Minimum (0)
    0x25, 0x73,  #   Logical Maximum (0x73)        F24
    0x05, 0x07,  #   Usage Page (Key Codes)
    0x19, 0x00,  #   Usage Minimum (0)
    0x29, 0x73,  #   Usage Maximum (0x73)          F24
    0x81, 0x00,  #   Input (Data, Array)           6 key slots
    0xC0,        # End Collection
))

_EMPTY_REPORT = bytes(8)
_BONDS_PATH = "bonds.txt"


def advertising_payload(name):
    """Connectable undirected advert: flags, keyboard appearance, HID, name."""
    name_b = name.encode("utf-8")
    payload = bytearray((
        0x02, 0x01, 0x06,                                  # LE General, BR/EDR not supported
        0x03, 0x19, 0xC1, 0x03,                            # Appearance: HID keyboard
        0x03, 0x03, 0x12, 0x18,                            # Complete UUID16: HID 0x1812
        len(name_b) + 1, 0x09,
    ))
    payload.extend(name_b)
    if len(payload) > 31:
        raise ValueError("advertising payload exceeds 31 bytes")
    return payload


def key_report(usage):
    """8-byte boot-style report: modifiers, reserved, six slots. No report id."""
    report = bytearray(_EMPTY_REPORT)
    if usage:
        report[2] = usage & 0xFF
    return report


def pnp_id():
    # USB-IF vendor source, then vid, pid, version, high byte first.
    vid, pid, version = 0x05AC, 0x820A, 0x0210
    return bytes((
        0x02,
        (vid >> 8) & 0xFF, vid & 0xFF,
        (pid >> 8) & 0xFF, pid & 0xFF,
        (version >> 8) & 0xFF, version & 0xFF,
    ))


class BondStore:
    """Secrets the NimBLE stack asks to save. Missing file means no bonds yet."""

    def __init__(self, path=_BONDS_PATH):
        self.path = path
        self._secrets = []
        self.corrupt = False
        self._load()

    def _load(self):
        try:
            with open(self.path) as handle:
                text = handle.read()
        except OSError:
            return
        parsed = []
        try:
            for line in text.split("\n"):
                if not line:
                    continue
                sec_s, key_h, val_h = line.split(" ")
                parsed.append((int(sec_s), binascii.unhexlify(key_h), binascii.unhexlify(val_h)))
        except (ValueError, IndexError):
            self.corrupt = True
            return
        self._secrets = parsed

    def _save(self):
        lines = []
        for sec, key, val in self._secrets:
            lines.append(
                "%d %s %s\n" % (sec, binascii.hexlify(key).decode(), binascii.hexlify(val).decode())
            )
        with open(self.path, "w") as handle:
            handle.write("".join(lines))

    def get(self, sec_type, index, key):
        if key is None:
            seen = 0
            for sec, _stored, val in self._secrets:
                if sec == sec_type:
                    if seen == index:
                        return val
                    seen += 1
            return None
        key = bytes(key)
        for sec, stored, val in self._secrets:
            if sec == sec_type and stored == key:
                return val
        return None

    def set(self, sec_type, key, value):
        key = bytes(key)
        kept = []
        replaced = False
        for sec, stored, stored_val in self._secrets:
            if sec == sec_type and stored == key:
                if value is not None and not replaced:
                    kept.append((sec_type, key, bytes(value)))
                    replaced = True
            else:
                kept.append((sec, stored, stored_val))
        if value is not None and not replaced:
            kept.append((sec_type, key, bytes(value)))
        self._secrets = kept
        self._save()
        return True


class BleKeyboard:
    def __init__(self, name):
        self.name = name
        self.connected = False
        self.encrypted = False
        self.conn_handle = None
        self._payload = advertising_payload(name)
        self._bonds = BondStore()
        self._ble = None
        self._h_input = None

    def start(self):
        if bluetooth is None:
            raise RuntimeError("This MicroPython build has no bluetooth module")
        if self._bonds.corrupt:
            print("bonds.txt jest uszkodzony. Parowanie od nowa.")

        ble = bluetooth.BLE()
        self._ble = ble
        ble.active(True)
        ble.config(gap_name=self.name)
        ble.config(
            bond=True,
            mitm=False,
            le_secure=False,
            io=_IO_CAPABILITY_NO_INPUT_OUTPUT,
        )
        ble.irq(self._irq)
        self._register(ble)
        self._advertise()

        _addr_type, addr = ble.config("mac")
        print("Adres BLE: %s" % ":".join("%02X" % b for b in bytes(addr)))

    def pair(self):
        if self.conn_handle is None:
            return
        self._ble.gap_pair(self.conn_handle)

    def tap(self, usage, hold_ms):
        if not self.connected or self.conn_handle is None:
            return False
        try:
            self._notify(key_report(usage))
        except OSError:
            return False
        time.sleep_ms(hold_ms)
        try:
            self._notify(key_report(0))
        except OSError:
            pass
        return True

    def release_all(self):
        if not self.connected or self.conn_handle is None:
            return
        try:
            self._notify(key_report(0))
        except OSError:
            pass

    def _notify(self, report):
        self._ble.gatts_notify(self.conn_handle, self._h_input, report)

    def _advertise(self):
        self._ble.gap_advertise(_ADV_INTERVAL_US, adv_data=self._payload)

    def _register(self, ble):
        # Flags are plain ints. Descriptors are flattened into the same handle tuple.
        read_write = _FLAG_READ | _FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE
        services = (
            (
                bluetooth.UUID(_HID_SERVICE),
                (
                    (bluetooth.UUID(0x2A4A), _FLAG_READ),
                    (bluetooth.UUID(0x2A4B), _FLAG_READ),
                    (bluetooth.UUID(0x2A4C), read_write),
                    (bluetooth.UUID(0x2A4E), read_write),
                    (
                        bluetooth.UUID(0x2A4D),
                        _FLAG_READ | _FLAG_NOTIFY,
                        ((bluetooth.UUID(0x2908), _FLAG_READ),),
                    ),
                    (
                        bluetooth.UUID(0x2A4D),
                        read_write,
                        ((bluetooth.UUID(0x2908), _FLAG_READ),),
                    ),
                ),
            ),
            (
                bluetooth.UUID(0x180A),
                (
                    (bluetooth.UUID(0x2A29), _FLAG_READ),
                    (bluetooth.UUID(0x2A50), _FLAG_READ),
                ),
            ),
            (
                bluetooth.UUID(0x180F),
                ((bluetooth.UUID(0x2A19), _FLAG_READ),),
            ),
        )
        handles = ble.gatts_register_services(services)
        if len(handles) != 3 or len(handles[0]) != 8 or len(handles[1]) != 2 or len(handles[2]) != 1:
            raise RuntimeError(
                "unexpected GATT handle layout: %s" % (tuple(len(group) for group in handles),)
            )
        (
            h_info,
            h_map,
            h_ctrl,
            h_proto,
            h_input,
            h_input_ref,
            _h_output,
            h_output_ref,
        ) = handles[0]
        h_man, h_pnp = handles[1]
        (h_bat,) = handles[2]
        self._h_input = h_input

        # The report map is longer than the default 20-byte value buffer.
        ble.gatts_set_buffer(h_map, len(_REPORT_MAP))
        ble.gatts_write(h_info, b"\x11\x01\x00\x01")  # HID 1.11, country 0, remote wake
        ble.gatts_write(h_map, _REPORT_MAP)
        ble.gatts_write(h_ctrl, b"\x00")
        ble.gatts_write(h_proto, b"\x01")  # report protocol
        ble.gatts_write(h_input, _EMPTY_REPORT)
        ble.gatts_write(h_input_ref, b"\x01\x01")  # report id 1, input
        ble.gatts_write(_h_output, b"\x00")
        ble.gatts_write(h_output_ref, b"\x01\x02")  # report id 1, output
        ble.gatts_write(h_man, b"TVAutoPilot")
        ble.gatts_write(h_pnp, pnp_id())
        ble.gatts_write(h_bat, b"\x64")

    def _irq(self, event, data):
        # Runs from the BLE callback. Update flags and answer secret requests.
        # Printing and key scheduling happen in the main loop.
        if event == _IRQ_CENTRAL_CONNECT:
            self.conn_handle = data[0]
            self.connected = True
            self.encrypted = False
            try:
                self._ble.gap_advertise(None)
            except OSError:
                pass
        elif event == _IRQ_CENTRAL_DISCONNECT:
            self.conn_handle = None
            self.connected = False
            self.encrypted = False
            try:
                self._advertise()
            except OSError:
                pass
        elif event == _IRQ_ENCRYPTION_UPDATE:
            _conn, encrypted, _authenticated, _bonded, _key_size = data
            self.encrypted = bool(encrypted)
        elif event == _IRQ_GET_SECRET:
            sec_type, index, key = data
            return self._bonds.get(sec_type, index, key)
        elif event == _IRQ_SET_SECRET:
            sec_type, key, value = data
            try:
                return self._bonds.set(sec_type, key, None if value is None else value)
            except OSError:
                return False
        elif event == _IRQ_PASSKEY_ACTION:
            # Just Works should not ask. Answer anyway so a peer that does
            # ask cannot leave pairing stuck.
            conn_handle, action, _passkey = data
            try:
                accept = 1 if action == _PASSKEY_ACTION_NUMERIC_COMPARISON else 0
                self._ble.gap_passkey(conn_handle, action, accept)
            except OSError:
                pass
        return None
