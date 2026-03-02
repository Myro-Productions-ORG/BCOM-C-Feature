/// Media Key Tap — intercepts Meta glasses tap via two parallel paths:
///
///   Path A: MPRemoteCommandCenter (AVRCP Play/Pause from Bluetooth)
///           Requires active audio session (AVAudioEngine) to claim Now Playing.
///
///   Path B: CGEventTap for kCGEventOtherMouseDown (type 25)
///           The WindowServer logs show the tap also appears as a HID button event.
///           Requires Accessibility permission.
///
/// Both paths are active simultaneously.  Whichever fires first wins.
/// Output clearly says which path caught the event.
///
/// Usage: ./media-key-tap [--url http://localhost:7766/api/toggle-active]

import AppKit
import AVFoundation
import Foundation
import MediaPlayer

// ── startup ───────────────────────────────────────────────────────────────────
print("media-key-tap starting  pid=\(ProcessInfo.processInfo.processIdentifier)")
print("Accessibility trusted: \(AXIsProcessTrusted())")
fflush(stdout)

// ── config ────────────────────────────────────────────────────────────────────
var toggleURL = "http://localhost:7766/api/toggle-active"
let cliArgs = CommandLine.arguments
for i in 0..<cliArgs.count where cliArgs[i] == "--url" && i + 1 < cliArgs.count {
    toggleURL = cliArgs[i + 1]
}
print("POST target: \(toggleURL)")
fflush(stdout)

// ── toggle (deduplicated — ignore second call within 500 ms) ──────────────────
var lastToggleTime: Date = .distantPast
func sendToggle(_ source: String) {
    let now = Date()
    guard now.timeIntervalSince(lastToggleTime) > 0.5 else {
        print("[\(source)] duplicate suppressed")
        fflush(stdout)
        return
    }
    lastToggleTime = now
    guard let url = URL(string: toggleURL) else { return }
    var req = URLRequest(url: url)
    req.httpMethod = "POST"
    req.timeoutInterval = 2.0
    URLSession.shared.dataTask(with: req) { _, resp, err in
        if let err {
            print("[\(source)] POST error: \(err.localizedDescription)")
        } else if let http = resp as? HTTPURLResponse {
            print("[\(source)] Toggle sent → HTTP \(http.statusCode)")
        }
        fflush(stdout)
    }.resume()
}

// ═══════════════════════════════════════════════════════════════════════════════
// PATH A — MPRemoteCommandCenter (AVRCP via Bluetooth)
// ═══════════════════════════════════════════════════════════════════════════════

// Start a silent audio engine so macOS accepts us as the Now Playing app.
// Without an active audio session, nowPlayingInfo is ignored and AVRCP
// commands continue routing to Music.app.
let engine = AVAudioEngine()
let player = AVAudioPlayerNode()
engine.attach(player)
let fmt = AVAudioFormat(standardFormatWithSampleRate: 44100, channels: 2)!
engine.connect(player, to: engine.mainMixerNode, format: fmt)
engine.mainMixerNode.outputVolume = 0.0   // silence

do {
    try engine.start()
    let buf = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: 4410)!
    buf.frameLength = 4410   // all zeros = silence
    player.scheduleBuffer(buf, at: nil, options: .loops)
    player.play()
    print("PATH A: AVAudioEngine running (silent)")
} catch {
    print("PATH A: AVAudioEngine failed: \(error) — AVRCP may not work")
}

MPNowPlayingInfoCenter.default().nowPlayingInfo = [
    MPMediaItemPropertyTitle:             "Bob" as AnyObject,
    MPMediaItemPropertyArtist:            "Voice Assistant" as AnyObject,
    MPNowPlayingInfoPropertyMediaType:    MPNowPlayingInfoMediaType.audio.rawValue as AnyObject,
    MPNowPlayingInfoPropertyPlaybackRate: 1.0 as AnyObject,
]
MPNowPlayingInfoCenter.default().playbackState = .playing

let cc = MPRemoteCommandCenter.shared()
for cmd in [cc.previousTrackCommand, cc.nextTrackCommand, cc.seekForwardCommand,
            cc.seekBackwardCommand, cc.skipForwardCommand, cc.skipBackwardCommand] {
    cmd.isEnabled = false
}
cc.playCommand.isEnabled = true
cc.playCommand.addTarget { _ in
    print("PATH A: AVRCP Play → toggle")
    fflush(stdout)
    sendToggle("AVRCP-play")
    return .success
}
cc.pauseCommand.isEnabled = true
cc.pauseCommand.addTarget { _ in
    print("PATH A: AVRCP Pause → toggle")
    fflush(stdout)
    sendToggle("AVRCP-pause")
    return .success
}
cc.togglePlayPauseCommand.isEnabled = true
cc.togglePlayPauseCommand.addTarget { _ in
    print("PATH A: AVRCP TogglePlayPause → toggle")
    fflush(stdout)
    sendToggle("AVRCP-toggle")
    return .success
}
print("PATH A: MPRemoteCommandCenter handlers registered")
fflush(stdout)

// ═══════════════════════════════════════════════════════════════════════════════
// PATH B — CGEventTap kCGEventOtherMouseDown (type 25)
// WindowServer logs show the tap also arrives as a HID button event.
// ═══════════════════════════════════════════════════════════════════════════════

// Mask: bit 14 (systemDefined media keys) | bit 25 (otherMouseDown) | bit 26 (otherMouseUp)
let tapMask: CGEventMask = (1 << 14) | (1 << 25) | (1 << 26)

let tapCB: CGEventTapCallBack = { _, type, cgEvent, _ -> Unmanaged<CGEvent>? in
    let t = type.rawValue
    if t == 25 {   // kCGEventOtherMouseDown
        let btn = cgEvent.getIntegerValueField(.mouseEventButtonNumber)
        print("PATH B: OtherMouseDown button=\(btn) → toggle")
        fflush(stdout)
        sendToggle("HIDButton-b\(btn)")
        return nil  // swallow
    }
    if t == 26 { return Unmanaged.passRetained(cgEvent) }  // up — ignore
    if t == 14, let ev = NSEvent(cgEvent: cgEvent), ev.subtype.rawValue == 8 {
        let d = ev.data1
        let kc = (d & 0xFFFF0000) >> 16
        let ks = (d & 0x0000FF00) >> 8
        if kc == 16, ks == 0xa {
            print("PATH B: keyboard play/pause → toggle")
            fflush(stdout)
            sendToggle("keyboard-media")
            return nil
        }
    }
    return Unmanaged.passRetained(cgEvent)
}

var tapCreated = false
for loc: CGEventTapLocation in [.cghidEventTap, .cgSessionEventTap] {
    if let tap = CGEvent.tapCreate(tap: loc, place: .headInsertEventTap,
                                    options: CGEventTapOptions(rawValue: 0)!,
                                    eventsOfInterest: tapMask,
                                    callback: tapCB, userInfo: nil),
       let src = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0) {
        CGEvent.tapEnable(tap: tap, enable: true)
        CFRunLoopAddSource(CFRunLoopGetMain(), src, .commonModes)
        let label = loc == .cghidEventTap ? "cghidEventTap" : "cgSessionEventTap"
        print("PATH B: CGEventTap created at \(label)")
        tapCreated = true
        break
    }
}
if !tapCreated {
    print("PATH B: CGEventTap FAILED (Accessibility not granted?) — only PATH A active")
}
fflush(stdout)

// ── run ───────────────────────────────────────────────────────────────────────
print("Both paths active — tap glasses to test.")
fflush(stdout)

signal(SIGINT) { _ in
    MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
    print("\nStopping.")
    exit(0)
}

Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { _ in
    print("heartbeat"); fflush(stdout)
}

let app = NSApplication.shared
app.setActivationPolicy(.prohibited)
app.run()
