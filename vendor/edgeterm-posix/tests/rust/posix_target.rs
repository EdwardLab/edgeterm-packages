use std::fs;
use std::os::unix::fs::MetadataExt;

fn main() {
    let metadata = fs::metadata("/").expect("root metadata");
    assert!(metadata.nlink() > 0);
    println!("posix-rust-target-ready");
}
