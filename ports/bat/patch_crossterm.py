from pathlib import Path
import sys


root = Path(sys.argv[1])


def replace(relative_path: str, old: str, new: str) -> None:
    path = root / relative_path
    content = path.read_text()
    if new in content:
        return
    if old not in content:
        raise RuntimeError(f"Expected source fragment not found in {relative_path}")
    path.write_text(content.replace(old, new))


def dedupe(relative_path: str, block: str) -> None:
    path = root / relative_path
    content = path.read_text()
    while f"{block}\n{block}" in content:
        content = content.replace(f"{block}\n{block}", block)
    path.write_text(content)


dedupe("src/cursor/sys.rs", "#[cfg(target_os = \"wasi\")]\npub use self::wasi::position;")
dedupe("src/cursor/sys.rs", "#[cfg(target_os = \"wasi\")]\npub(crate) mod wasi;")
dedupe("src/event/sys.rs", "#[cfg(target_os = \"wasi\")]\npub(crate) mod wasi;")
dedupe("src/event/read.rs", "#[cfg(target_os = \"wasi\")]\nuse crate::event::sys::wasi::WasiEventSource;")
dedupe(
    "src/terminal/sys.rs",
    "#[cfg(target_os = \"wasi\")]\n#[cfg(feature = \"events\")]\npub use self::wasi::supports_keyboard_enhancement;",
)
dedupe(
    "src/terminal/sys.rs",
    "#[cfg(target_os = \"wasi\")]\npub(crate) use self::wasi::{\n    disable_raw_mode, enable_raw_mode, is_raw_mode_enabled, size, window_size,\n};",
)
dedupe("src/terminal/sys.rs", "#[cfg(target_os = \"wasi\")]\nmod wasi;")
dedupe(
    "src/terminal.rs",
    "    #[cfg(target_os = \"wasi\")]\n    {\n        Ok(sys::is_raw_mode_enabled())\n    }",
)


replace(
    "src/cursor/sys.rs",
    "#[cfg(windows)]\npub use self::windows::position;",
    "#[cfg(windows)]\npub use self::windows::position;\n#[cfg(target_os = \"wasi\")]\npub use self::wasi::position;",
)
replace(
    "src/cursor/sys.rs",
    "#[cfg(unix)]\n#[cfg(feature = \"events\")]\npub(crate) mod unix;",
    "#[cfg(unix)]\n#[cfg(feature = \"events\")]\npub(crate) mod unix;\n#[cfg(target_os = \"wasi\")]\npub(crate) mod wasi;",
)
replace(
    "src/terminal/sys.rs",
    "#[cfg(windows)]\n#[cfg(feature = \"events\")]\npub use self::windows::supports_keyboard_enhancement;",
    "#[cfg(windows)]\n#[cfg(feature = \"events\")]\npub use self::windows::supports_keyboard_enhancement;\n#[cfg(target_os = \"wasi\")]\n#[cfg(feature = \"events\")]\npub use self::wasi::supports_keyboard_enhancement;",
)
replace(
    "src/terminal/sys.rs",
    "#[cfg(windows)]\npub(crate) use self::windows::{",
    "#[cfg(target_os = \"wasi\")]\npub(crate) use self::wasi::{\n    disable_raw_mode, enable_raw_mode, is_raw_mode_enabled, size, window_size,\n};\n#[cfg(windows)]\npub(crate) use self::windows::{",
)
replace(
    "src/terminal/sys.rs",
    "#[cfg(unix)]\nmod unix;",
    "#[cfg(unix)]\nmod unix;\n#[cfg(target_os = \"wasi\")]\nmod wasi;",
)
replace(
    "src/event/sys.rs",
    "#[cfg(windows)]\npub(crate) mod windows;",
    "#[cfg(windows)]\npub(crate) mod windows;\n#[cfg(target_os = \"wasi\")]\npub(crate) mod wasi;",
)
replace(
    "src/event/read.rs",
    "#[cfg(windows)]\nuse crate::event::source::windows::WindowsEventSource;",
    "#[cfg(windows)]\nuse crate::event::source::windows::WindowsEventSource;\n#[cfg(target_os = \"wasi\")]\nuse crate::event::sys::wasi::WasiEventSource;",
)
replace(
    "src/event/read.rs",
    "#[cfg(unix)]\n        let source = UnixInternalEventSource::new();",
    "#[cfg(unix)]\n        let source = UnixInternalEventSource::new();\n        #[cfg(target_os = \"wasi\")]\n        let source = WasiEventSource::new();",
)
replace(
    "src/event/filter.rs",
    "    #[cfg(windows)]\n    fn eval(&self, _: &InternalEvent) -> bool {",
    "    #[cfg(any(windows, target_os = \"wasi\"))]\n    fn eval(&self, _: &InternalEvent) -> bool {",
)
replace(
    "src/terminal.rs",
    "    #[cfg(windows)]\n    {\n        sys::is_raw_mode_enabled()\n    }",
    "    #[cfg(windows)]\n    {\n        sys::is_raw_mode_enabled()\n    }\n\n    #[cfg(target_os = \"wasi\")]\n    {\n        Ok(sys::is_raw_mode_enabled())\n    }",
)
