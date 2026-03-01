//! Audio capture module — mic input via cpal, outputs PCM frames to a channel.

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::StreamConfig;
use tokio::sync::mpsc;
use tracing::{error, info};

pub const SAMPLE_RATE: u32 = 16_000;
pub const CHANNELS: u16 = 1;
pub const FRAME_DURATION_MS: u32 = 30;
pub const FRAME_SAMPLES: usize = (SAMPLE_RATE * FRAME_DURATION_MS / 1000) as usize;

pub fn start_capture(
    device_name: Option<&str>,
    tx: mpsc::UnboundedSender<Vec<i16>>,
) -> Result<cpal::Stream, anyhow::Error> {
    let host = cpal::default_host();

    let device = match device_name {
        Some(name) => {
            let mut found = None;
            for d in host.input_devices()? {
                if let Ok(n) = d.name() {
                    if n == name {
                        found = Some(d);
                        break;
                    }
                }
            }
            found.ok_or_else(|| anyhow::anyhow!("Input device '{}' not found", name))?
        }
        None => host
            .default_input_device()
            .ok_or_else(|| anyhow::anyhow!("No default input device available"))?,
    };

    let dev_name = device.name().unwrap_or_else(|_| "unknown".into());
    info!("Using input device: {}", dev_name);

    // Find best supported config: prefer 16kHz mono, fall back to device default
    let supported: Vec<_> = device.supported_input_configs()?.collect();
    info!("Supported configs: {:?}", supported);

    let default_config = device.default_input_config()?;
    let native_rate = default_config.sample_rate().0;
    let native_channels = default_config.channels();
    info!("Device native: {}Hz, {} ch, {:?}", native_rate, native_channels, default_config.sample_format());

    let config = StreamConfig {
        channels: native_channels,
        sample_rate: cpal::SampleRate(native_rate),
        buffer_size: cpal::BufferSize::Default,
    };

    let need_resample = native_rate != SAMPLE_RATE;
    let need_downmix = native_channels > 1;
    let ratio = if need_resample { SAMPLE_RATE as f64 / native_rate as f64 } else { 1.0 };
    let ch = native_channels as usize;

    let stream = device.build_input_stream::<f32, _, _>(
        &config,
        move |data, _info| {
            // Downmix to mono if needed
            let mono: Vec<f32> = if need_downmix {
                data.chunks(ch)
                    .map(|frame| frame.iter().sum::<f32>() / ch as f32)
                    .collect()
            } else {
                data.to_vec()
            };

            // Resample to 16kHz if needed (simple linear interpolation)
            let resampled: Vec<f32> = if need_resample {
                let out_len = (mono.len() as f64 * ratio) as usize;
                (0..out_len)
                    .map(|i| {
                        let src_idx = i as f64 / ratio;
                        let lo = src_idx as usize;
                        let hi = (lo + 1).min(mono.len() - 1);
                        let frac = (src_idx - lo as f64) as f32;
                        mono[lo] * (1.0 - frac) + mono[hi] * frac
                    })
                    .collect()
            } else {
                mono
            };

            // Convert f32 -> i16
            let converted: Vec<i16> = resampled
                .iter()
                .map(|&s| (s.clamp(-1.0_f32, 1.0_f32) * 32767.0) as i16)
                .collect();
            let _ = tx.send(converted);
        },
        |err| error!("Audio stream error: {}", err),
        None,
    )?;

    stream.play()?;
    info!("Audio capture started: native {}Hz {}ch -> 16kHz mono i16", native_rate, native_channels);
    Ok(stream)
}

pub fn list_devices() {
    let host = cpal::default_host();
    println!("Available input devices:");
    if let Ok(devices) = host.input_devices() {
        for d in devices {
            if let Ok(name) = d.name() {
                let is_default = host
                    .default_input_device()
                    .and_then(|dd| dd.name().ok())
                    .map(|dn| dn == name)
                    .unwrap_or(false);
                println!(
                    "  {} {}",
                    name,
                    if is_default { "(default)" } else { "" }
                );
            }
        }
    }
}
