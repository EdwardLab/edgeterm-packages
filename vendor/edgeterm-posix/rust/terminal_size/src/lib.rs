use std::os::unix::io::{AsFd, AsRawFd, BorrowedFd, RawFd};


#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct Width(pub u16);

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct Height(pub u16);


#[repr(C)]
#[derive(Default)]
struct WindowSize {
    rows: u16,
    columns: u16,
    x_pixels: u16,
    y_pixels: u16,
}


const TIOCGWINSZ: i32 = 0x101;


unsafe extern "C" {
    fn ioctl(fd: i32, request: i32, ...) -> i32;
}


pub fn terminal_size() -> Option<(Width, Height)> {
    terminal_size_of(std::io::stdout())
        .or_else(|| terminal_size_of(std::io::stderr()))
        .or_else(|| terminal_size_of(std::io::stdin()))
}


pub fn terminal_size_of<Fd: AsFd>(fd: Fd) -> Option<(Width, Height)> {
    let mut size = WindowSize::default();
    let result = unsafe { ioctl(fd.as_fd().as_raw_fd(), TIOCGWINSZ, &mut size) };
    if result == 0 && size.rows > 0 && size.columns > 0 {
        Some((Width(size.columns), Height(size.rows)))
    } else {
        None
    }
}


#[deprecated(
    note = "Use terminal_size_of with BorrowedFd::borrow_raw instead of a raw descriptor"
)]
pub unsafe fn terminal_size_using_fd(fd: RawFd) -> Option<(Width, Height)> {
    terminal_size_of(BorrowedFd::borrow_raw(fd))
}
