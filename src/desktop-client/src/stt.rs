//! WebSocket client for the STT service.

use futures_util::{SinkExt, StreamExt};
use serde::Deserialize;
use std::net::TcpStream as StdTcpStream;
use tokio::net::TcpStream;
use tokio_tungstenite::{client_async, tungstenite::Message};
use tracing::{debug, error, info, warn};

#[derive(Debug, Deserialize)]
pub struct SttSegment {
    pub start: Option<f64>,
    pub end: Option<f64>,
    pub text: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct SttResult {
    pub r#type: String,
    pub text: Option<String>,
    pub segments: Option<Vec<SttSegment>>,
    pub language: Option<String>,
    pub duration: Option<f64>,
    pub processing_ms: Option<u64>,
    pub message: Option<String>,
}

pub struct SttClient {
    ws_url: String,
    host: String,
    port: u16,
}

impl SttClient {
    pub fn new(endpoint: &str) -> Self {
        let without_scheme = endpoint
            .strip_prefix("ws://")
            .or_else(|| endpoint.strip_prefix("wss://"))
            .unwrap_or(endpoint);
        let host_port = without_scheme.split('/').next().unwrap_or("10.0.0.10:8765");
        let parts: Vec<&str> = host_port.split(':').collect();
        let host = parts.first().unwrap_or(&"10.0.0.10").to_string();
        let port: u16 = parts.get(1).and_then(|p| p.parse().ok()).unwrap_or(8765);

        Self {
            ws_url: endpoint.to_string(),
            host,
            port,
        }
    }

    pub async fn transcribe(&self, audio_frames: Vec<Vec<i16>>) -> Result<String, anyhow::Error> {
        let addr = format!("{}:{}", self.host, self.port);
        debug!("Opening TCP (std::net) to {}", addr);

        // Use blocking std::net connect in a spawn_blocking to bypass any tokio resolver weirdness
        let addr_clone = addr.clone();
        let std_stream = tokio::task::spawn_blocking(move || {
            StdTcpStream::connect(&addr_clone)
        })
        .await?
        .map_err(|e| {
            error!("std TCP connect to {} failed: {}", addr, e);
            anyhow::anyhow!("TCP connect failed: {}", e)
        })?;

        std_stream.set_nonblocking(true)?;
        let tcp_stream = TcpStream::from_std(std_stream)?;
        debug!("TCP connected to {}", addr);

        let (ws_stream, _resp) = client_async(&self.ws_url, tcp_stream).await.map_err(|e| {
            error!("WebSocket handshake failed: {}", e);
            anyhow::anyhow!("WebSocket handshake failed: {}", e)
        })?;
        debug!("WebSocket handshake complete");

        let (mut write, mut read) = ws_stream.split();

        if let Some(Ok(msg)) = read.next().await {
            if let Message::Text(txt) = msg {
                let parsed: SttResult = serde_json::from_str(&txt)?;
                if parsed.r#type != "ready" {
                    warn!("Expected 'ready', got '{}'", parsed.r#type);
                }
            }
        }
        debug!("STT connection ready");

        for frame in &audio_frames {
            let bytes: Vec<u8> = frame.iter().flat_map(|&s| s.to_le_bytes()).collect();
            write.send(Message::Binary(bytes.into())).await?;
        }

        write
            .send(Message::Text(
                serde_json::json!({"type": "end"}).to_string().into(),
            ))
            .await?;
        debug!("Sent {} frames + end signal", audio_frames.len());

        let mut full_text = String::new();
        while let Some(Ok(msg)) = read.next().await {
            if let Message::Text(txt) = msg {
                let result: SttResult = serde_json::from_str(&txt)?;
                match result.r#type.as_str() {
                    "segment" => {
                        if let Some(text) = &result.text {
                            debug!("Segment: {}", text);
                        }
                    }
                    "final" => {
                        full_text = result.text.unwrap_or_default();
                        if let Some(ms) = result.processing_ms {
                            info!("STT: {}ms processing", ms);
                        }
                        break;
                    }
                    "error" => {
                        let msg = result.message.unwrap_or_else(|| "unknown".into());
                        error!("STT error: {}", msg);
                        return Err(anyhow::anyhow!("STT error: {}", msg));
                    }
                    other => {
                        debug!("STT unknown message type: {}", other);
                    }
                }
            }
        }

        let _ = write.close().await;
        Ok(full_text)
    }
}
