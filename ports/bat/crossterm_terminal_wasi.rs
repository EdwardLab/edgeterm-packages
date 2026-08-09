use crate::terminal::WindowSize;
use std::{env, io};

fn dimension(name: &str, default: u16) -> u16 {
    env::var(name)
        .ok()
        .and_then(|value| value.parse::<u16>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(default)
}

pub(crate) fn is_raw_mode_enabled() -> bool {
    false
}

pub(crate) fn enable_raw_mode() -> io::Result<()> {
    Ok(())
}

pub(crate) fn disable_raw_mode() -> io::Result<()> {
    Ok(())
}

pub(crate) fn size() -> io::Result<(u16, u16)> {
    Ok((dimension("COLUMNS", 80), dimension("LINES", 24)))
}

pub(crate) fn window_size() -> io::Result<WindowSize> {
    let (columns, rows) = size()?;
    Ok(WindowSize {
        columns,
        rows,
        width: 0,
        height: 0,
    })
}

#[cfg(feature = "events")]
pub fn supports_keyboard_enhancement() -> io::Result<bool> {
    Ok(false)
}
