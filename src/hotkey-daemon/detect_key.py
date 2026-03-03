"""Diagnostic — detects media key events. Tap the glasses. Ctrl+C to quit."""
import signal
import AppKit
from Foundation import NSRunLoop, NSDate

# NSSystemDefined event mask = 1 << 14
NS_SYSTEM_DEFINED_MASK = 1 << 14

def handler(event):
    if event.subtype() == 8:
        data = event.data1()
        key_code = (data & 0xFFFF0000) >> 16
        key_state = (data & 0x0000FF00) >> 8
        print(f"Media key: code={key_code}  state={key_state}", flush=True)

AppKit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(NS_SYSTEM_DEFINED_MASK, handler)

running = [True]
signal.signal(signal.SIGINT, lambda *_: running.__setitem__(0, False))

print("Monitoring — tap glasses now. Ctrl+C to quit.")
while running[0]:
    NSRunLoop.mainRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))

print("Done.")
