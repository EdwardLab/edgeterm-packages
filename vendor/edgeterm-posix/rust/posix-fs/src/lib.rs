use std::fs::{FileType, Metadata, Permissions};
use std::time::{SystemTime, UNIX_EPOCH};

pub trait PermissionsExt {
    fn mode(&self) -> u32;
}

impl PermissionsExt for Permissions {
    fn mode(&self) -> u32 {
        if self.readonly() { 0o444 } else { 0o666 }
    }
}

pub trait FileTypeExt {
    fn is_fifo(&self) -> bool;
    fn is_char_device(&self) -> bool;
    fn is_block_device(&self) -> bool;
    fn is_socket(&self) -> bool;
}

impl FileTypeExt for FileType {
    fn is_fifo(&self) -> bool {
        false
    }

    fn is_char_device(&self) -> bool {
        false
    }

    fn is_block_device(&self) -> bool {
        false
    }

    fn is_socket(&self) -> bool {
        false
    }
}

pub trait MetadataExt {
    fn dev(&self) -> u64;
    fn ino(&self) -> u64;
    fn mode(&self) -> u32;
    fn nlink(&self) -> u64;
    fn uid(&self) -> u32;
    fn gid(&self) -> u32;
    fn rdev(&self) -> u64;
    fn size(&self) -> u64;
    fn atime(&self) -> i64;
    fn atime_nsec(&self) -> i64;
    fn mtime(&self) -> i64;
    fn mtime_nsec(&self) -> i64;
    fn ctime(&self) -> i64;
    fn ctime_nsec(&self) -> i64;
    fn blksize(&self) -> u64;
    fn blocks(&self) -> u64;
}

fn timestamp(time: Option<SystemTime>) -> (i64, i64) {
    let duration = time
        .and_then(|value| value.duration_since(UNIX_EPOCH).ok())
        .unwrap_or_default();
    (duration.as_secs() as i64, duration.subsec_nanos() as i64)
}

impl MetadataExt for Metadata {
    fn dev(&self) -> u64 { 0 }
    fn ino(&self) -> u64 { 0 }
    fn mode(&self) -> u32 {
        let kind = if self.is_dir() { 0o040000 } else { 0o100000 };
        kind | self.permissions().mode()
    }
    fn nlink(&self) -> u64 { 1 }
    fn uid(&self) -> u32 { 0 }
    fn gid(&self) -> u32 { 0 }
    fn rdev(&self) -> u64 { 0 }
    fn size(&self) -> u64 { self.len() }
    fn atime(&self) -> i64 { timestamp(self.accessed().ok()).0 }
    fn atime_nsec(&self) -> i64 { timestamp(self.accessed().ok()).1 }
    fn mtime(&self) -> i64 { timestamp(self.modified().ok()).0 }
    fn mtime_nsec(&self) -> i64 { timestamp(self.modified().ok()).1 }
    fn ctime(&self) -> i64 { timestamp(self.created().ok().or_else(|| self.modified().ok())).0 }
    fn ctime_nsec(&self) -> i64 { timestamp(self.created().ok().or_else(|| self.modified().ok())).1 }
    fn blksize(&self) -> u64 { 4096 }
    fn blocks(&self) -> u64 { self.len().div_ceil(512) }
}

pub fn major(device: u64) -> u32 {
    ((device >> 8) & 0xfff) as u32
}

pub fn minor(device: u64) -> u32 {
    (device & 0xff) as u32
}

pub fn reset_sigpipe() {}
