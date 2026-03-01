//! Bob Desktop Client — Rust CLI
//!
//! Captures mic audio on the M4 Pro, runs energy-based VAD,
//! streams voiced segments to the STT daemon at ws://10.0.0.10:8765,
//! and emits transcripts as newline-delimited JSON on stdout.

mod audio;
mod control;
mod stt;
mod vad;

use clap::{Parser, Subcommand};
use serde::Serialize;
use tokio::sync::mpsc;
use tracing::{error, info, warn};
use tracing_subscriber::EnvFilter;

use audio::FRAME_SAMPLES;
use vad::{EnergyVad, VadEvent};

const DEFAULT_STT_ENDPOINT: &str = "ws://127.0.0.1:8765/ws/transcribe";

#[derive(Parser, Debug)]
#[command(name = "bob-voice-cli", version, about = "Bob Desktop Client — mic + VAD + STT")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand, Debug)]
enum Commands {
    /// Start listening: capture mic → VAD → STT → JSON transcripts
    Listen {
        /// STT WebSocket endpoint
        #[arg(long, default_value = DEFAULT_STT_ENDPOINT)]
        stt_endpoint: String,

        /// Input device name (uses system default if omitted)
        #[arg(long)]
        device: Option<String>,

        /// VAD sensitivity 0.0–1.0 (higher = more sensitive)
        #[arg(long, default_value_t = 0.5)]
        vad_sensitivity: f32,

        /// Trailing silence in ms before ending an utterance
        #[arg(long, default_value_t = 600)]
        silence_ms: u32,

        /// Orchestrator control WebSocket URL
        #[arg(long, default_value = "ws://127.0.0.1:8766/ws/control")]
        orchestrator_url: String,
    },
    /// List available audio input devices
    Devices,
}

#[derive(Serialize)]
struct TranscriptEvent {
    r#type: String,
    text: String,
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .with_target(false)
        .init();

    let cli = Cli::parse();

    match cli.command {
        Commands::Devices => {
            audio::list_devices();
        }
        Commands::Listen {
            stt_endpoint,
            device,
            vad_sensitivity,
            silence_ms,
            orchestrator_url,
        } => {
            if let Err(e) = run_listen(&stt_endpoint, &orchestrator_url, device.as_deref(), vad_sensitivity, silence_ms).await {
                error!("Fatal: {}", e);
                std::process::exit(1);
            }
        }
    }
}

async fn run_listen(
    stt_endpoint: &str,
    orchestrator_url: &str,
    device: Option<&str>,
    vad_sensitivity: f32,
    silence_ms: u32,
) -> Result<(), anyhow::Error> {
    info!("Bob voice CLI starting");
    info!("STT endpoint: {}", stt_endpoint);
    info!("VAD sensitivity: {}", vad_sensitivity);

    let (audio_tx, mut audio_rx) = mpsc::unbounded_channel::<Vec<i16>>();

    // Start mic capture (must keep _stream alive)
    let _stream = audio::start_capture(device, audio_tx)?;
    info!("Mic capture active. Listening...");

    let stt_client = stt::SttClient::new(stt_endpoint);

    // Control channel — mode watch + barge-in signal sender
    let (mode_tx, mode_rx) = tokio::sync::watch::channel(control::ControlMode::Normal);
    let (barge_in_tx, barge_in_rx) = tokio::sync::mpsc::unbounded_channel::<()>();

    let ctrl_url = orchestrator_url.to_string();
    tokio::spawn(async move {
        if let Err(e) = control::run_control_channel(&ctrl_url, mode_tx, barge_in_rx).await {
            warn!("Control channel error: {}", e);
        }
    });

    let mut vad = EnergyVad::new(
        vad_sensitivity,
        audio::SAMPLE_RATE,
        audio::FRAME_DURATION_MS,
        300,         // 300ms pre-roll
        silence_ms,  // trailing silence
    );

    // Accumulator for re-framing cpal's variable-size buffers into fixed frames
    let mut sample_buf: Vec<i16> = Vec::with_capacity(FRAME_SAMPLES * 2);
    // Utterance buffer: collects all frames (pre-roll + speech) for one utterance
    let mut utterance_frames: Vec<Vec<i16>> = Vec::new();
    let mut is_in_utterance = false;

    loop {
        tokio::select! {
            Some(chunk) = audio_rx.recv() => {
                sample_buf.extend_from_slice(&chunk);

                // Process complete frames
                while sample_buf.len() >= FRAME_SAMPLES {
                    let frame: Vec<i16> = sample_buf.drain(..FRAME_SAMPLES).collect();
                    let event = vad.process_frame(&frame);

                    match event {
                        VadEvent::SpeechStart { pre_roll } => {
                            let mode = *mode_rx.borrow();
                            if mode == control::ControlMode::BargeIn {
                                info!("Barge-in detected (TTS active)");
                                let _ = barge_in_tx.send(());
                            }
                            info!("Speech detected");
                            is_in_utterance = true;
                            utterance_frames.clear();
                            // Include pre-roll audio
                            utterance_frames.extend(pre_roll);
                            utterance_frames.push(frame);
                        }
                        VadEvent::Speech => {
                            if is_in_utterance {
                                utterance_frames.push(frame);
                            }
                        }
                        VadEvent::SpeechEnd => {
                            if is_in_utterance {
                                info!("Speech ended, {} frames captured", utterance_frames.len());
                                is_in_utterance = false;

                                let frames = std::mem::take(&mut utterance_frames);
                                match stt_client.transcribe(frames).await {
                                    Ok(text) => {
                                        if !text.is_empty() {
                                            let event = TranscriptEvent {
                                                r#type: "final".to_string(),
                                                text: text.clone(),
                                            };
                                            // Emit JSON line to stdout
                                            if let Ok(json) = serde_json::to_string(&event) {
                                                println!("{}", json);
                                            }
                                            info!("Transcript: {}", text);
                                        }
                                    }
                                    Err(e) => {
                                        warn!("STT failed: {}. Retrying on next utterance.", e);
                                    }
                                }
                            }
                        }
                        VadEvent::Silence => {}
                    }
                }
            }
            // Graceful shutdown on Ctrl+C
            _ = tokio::signal::ctrl_c() => {
                info!("Shutting down.");
                break;
            }
        }
    }

    Ok(())
}
