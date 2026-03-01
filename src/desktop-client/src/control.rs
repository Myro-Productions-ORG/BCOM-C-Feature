// src/desktop-client/src/control.rs
//! Bidirectional control channel to the orchestrator.
//!
//! Receives: {"type":"tts_start"} / {"type":"tts_stop"}
//! Sends:    {"type":"barge_in"} / {"type":"ping"}

use anyhow::Result;
use futures_util::{SinkExt, StreamExt};
use serde::Deserialize;
use tokio::sync::watch;
use tokio_tungstenite::{connect_async, tungstenite::Message};
use tracing::{info, warn};

#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub enum ControlMode {
    #[default]
    Normal,
    BargeIn,
}

impl ControlMode {
    /// Silero confidence threshold for speech detection.
    /// Raised during TTS playback so only genuine barge-in triggers.
    pub fn silero_threshold(&self) -> f32 {
        match self {
            ControlMode::Normal => 0.5,
            ControlMode::BargeIn => 0.85,
        }
    }
}

#[derive(Deserialize)]
struct ControlMessage {
    r#type: String,
}

/// Spawns a tokio task that:
/// - Connects to the orchestrator control WebSocket
/// - Updates `mode_tx` when TTS state changes
/// - Sends barge_in when `barge_in_rx` fires
pub async fn run_control_channel(
    url: &str,
    mode_tx: watch::Sender<ControlMode>,
    mut barge_in_rx: tokio::sync::mpsc::UnboundedReceiver<()>,
) -> Result<()> {
    let (ws_stream, _) = connect_async(url).await?;
    let (mut write, mut read) = ws_stream.split();
    info!("Control channel connected to {}", url);

    loop {
        tokio::select! {
            Some(msg) = read.next() => {
                match msg? {
                    Message::Text(txt) => {
                        if let Ok(ctrl) = serde_json::from_str::<ControlMessage>(&txt) {
                            match ctrl.r#type.as_str() {
                                "tts_start" => {
                                    info!("TTS started — entering barge-in mode");
                                    let _ = mode_tx.send(ControlMode::BargeIn);
                                }
                                "tts_stop" => {
                                    info!("TTS stopped — returning to normal mode");
                                    let _ = mode_tx.send(ControlMode::Normal);
                                }
                                "pong" => {}
                                other => warn!("Unknown control message: {}", other),
                            }
                        }
                    }
                    Message::Close(_) => {
                        warn!("Orchestrator closed control channel");
                        break;
                    }
                    _ => {}
                }
            }
            Some(()) = barge_in_rx.recv() => {
                let msg = serde_json::json!({"type": "barge_in"}).to_string();
                write.send(Message::Text(msg.into())).await?;
                info!("Sent barge_in to orchestrator");
            }
            else => break,
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_control_mode_default() {
        let mode = ControlMode::default();
        assert_eq!(mode, ControlMode::Normal);
    }

    #[test]
    fn test_barge_in_threshold_raised_in_tts_mode() {
        let mode = ControlMode::BargeIn;
        assert!(mode.silero_threshold() > ControlMode::Normal.silero_threshold());
    }
}
