use crate::{Clircle, Stdio};

use std::convert::TryFrom;
use std::fs::File;
use std::hash::{Hash, Hasher};
use std::io;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT_IDENTIFIER: AtomicU64 = AtomicU64::new(1);

#[derive(Debug)]
pub(crate) struct Identifier {
    id: u64,
    file: Option<File>,
}

impl Clircle for Identifier {
    fn into_inner(mut self) -> Option<File> {
        self.file.take()
    }
}

impl TryFrom<Stdio> for Identifier {
    type Error = io::Error;

    fn try_from(_stdio: Stdio) -> Result<Self, Self::Error> {
        Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "standard stream identity is unavailable",
        ))
    }
}

impl TryFrom<File> for Identifier {
    type Error = io::Error;

    fn try_from(file: File) -> Result<Self, Self::Error> {
        Ok(Self {
            id: NEXT_IDENTIFIER.fetch_add(1, Ordering::Relaxed),
            file: Some(file),
        })
    }
}

impl PartialEq for Identifier {
    fn eq(&self, other: &Self) -> bool {
        self.id == other.id
    }
}

impl Eq for Identifier {}

impl Hash for Identifier {
    fn hash<H: Hasher>(&self, state: &mut H) {
        self.id.hash(state);
    }
}
