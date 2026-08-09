use std::{io, time::Duration};

use crate::event::{source::EventSource, InternalEvent};

pub(crate) struct WasiEventSource;

impl WasiEventSource {
    pub(crate) fn new() -> io::Result<Self> {
        Ok(Self)
    }
}

impl EventSource for WasiEventSource {
    fn try_read(&mut self, _timeout: Option<Duration>) -> io::Result<Option<InternalEvent>> {
        Ok(None)
    }
}
