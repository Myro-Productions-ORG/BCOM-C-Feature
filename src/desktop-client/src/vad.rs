//! Energy-based Voice Activity Detection.
//!
//! Simple RMS threshold VAD with pre-roll buffering and trailing silence detection.
//! Good enough for near-field mic on the M4 Pro; swap for WebRTC VAD or Silero later.

use std::collections::VecDeque;

#[derive(Debug, Clone, PartialEq)]
pub enum VadEvent {
    Silence,
    SpeechStart { pre_roll: Vec<Vec<i16>> },
    Speech,
    SpeechEnd,
}

#[derive(Debug, Clone, Copy, PartialEq)]
enum State {
    Idle,
    Speaking,
    Trailing,
}

pub struct EnergyVad {
    threshold: f32,
    state: State,
    silence_frames: usize,
    max_silence_frames: usize,
    pre_roll: VecDeque<Vec<i16>>,
    pre_roll_max: usize,
}

impl EnergyVad {
    /// Create a new VAD.
    ///
    /// - `sensitivity`: 0.0–1.0. Higher = triggers on quieter speech.
    ///   Internally mapped to an RMS threshold.
    /// - `sample_rate`: samples per second (16000).
    /// - `frame_duration_ms`: duration of each frame passed to `process_frame`.
    /// - `pre_roll_ms`: how much audio before speech onset to include.
    /// - `trailing_silence_ms`: silence after speech before we call it done.
    pub fn new(
        sensitivity: f32,
        _sample_rate: u32,
        frame_duration_ms: u32,
        pre_roll_ms: u32,
        trailing_silence_ms: u32,
    ) -> Self {
        // Map sensitivity [0,1] to RMS threshold.
        // sensitivity=0 → threshold ~800 (need loud speech)
        // sensitivity=1 → threshold ~50 (very sensitive)
        let threshold = 800.0 - (sensitivity.clamp(0.0, 1.0) * 750.0);

        let _frames_per_sec = 1000 / frame_duration_ms;
        let pre_roll_frames = (pre_roll_ms / frame_duration_ms) as usize;
        let silence_frames = (trailing_silence_ms / frame_duration_ms) as usize;

        Self {
            threshold,
            state: State::Idle,
            silence_frames: 0,
            max_silence_frames: silence_frames,
            pre_roll: VecDeque::with_capacity(pre_roll_frames + 1),
            pre_roll_max: pre_roll_frames,
        }
    }

    pub fn process_frame(&mut self, frame: &[i16]) -> VadEvent {
        let rms = compute_rms(frame);
        let is_speech = rms > self.threshold;

        match self.state {
            State::Idle => {
                self.pre_roll.push_back(frame.to_vec());
                if self.pre_roll.len() > self.pre_roll_max {
                    self.pre_roll.pop_front();
                }
                if is_speech {
                    self.state = State::Speaking;
                    self.silence_frames = 0;
                    let pre_roll: Vec<Vec<i16>> = self.pre_roll.drain(..).collect();
                    VadEvent::SpeechStart { pre_roll }
                } else {
                    VadEvent::Silence
                }
            }
            State::Speaking | State::Trailing => {
                if is_speech {
                    self.state = State::Speaking;
                    self.silence_frames = 0;
                    VadEvent::Speech
                } else {
                    self.silence_frames += 1;
                    self.state = State::Trailing;
                    if self.silence_frames >= self.max_silence_frames {
                        self.state = State::Idle;
                        self.silence_frames = 0;
                        VadEvent::SpeechEnd
                    } else {
                        VadEvent::Speech
                    }
                }
            }
        }
    }

    pub fn reset(&mut self) {
        self.state = State::Idle;
        self.silence_frames = 0;
        self.pre_roll.clear();
    }
}

fn compute_rms(samples: &[i16]) -> f32 {
    if samples.is_empty() {
        return 0.0;
    }
    let sum_sq: f64 = samples.iter().map(|&s| (s as f64) * (s as f64)).sum();
    (sum_sq / samples.len() as f64).sqrt() as f32
}
