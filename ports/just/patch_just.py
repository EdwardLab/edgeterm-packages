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


replace(
    "src/platform.rs",
    "#[cfg(windows)]\nmod windows;",
    "#[cfg(windows)]\nmod windows;\n\n#[cfg(target_os = \"wasi\")]\nmod wasi;",
)
replace(
    "src/signal.rs",
    "#[cfg(not(windows))]\nimpl From<Signal> for nix::sys::signal::Signal {",
    "#[cfg(all(not(windows), not(target_os = \"wasi\")))]\nimpl From<Signal> for nix::sys::signal::Signal {",
)
replace(
    "src/signal_handler.rs",
    "        #[cfg(not(windows))]\n        for &child in self.children.keys() {",
    "        #[cfg(all(not(windows), not(target_os = \"wasi\")))]\n        for &child in self.children.keys() {",
)
replace(
    "src/request.rs",
    "EnvironmentVariable(Option<OsString>)",
    "EnvironmentVariable(Option<String>)",
)
replace(
    "src/subcommand.rs",
    "Response::EnvironmentVariable(env::var_os(key))",
    "Response::EnvironmentVariable(env::var_os(key).map(|value| value.to_string_lossy().into_owned()))",
)
replace(
    "src/subcommand.rs",
    "      #[cfg(not(windows))]\n      Request::Signal => {",
    "      #[cfg(all(not(windows), not(target_os = \"wasi\")))]\n      Request::Signal => {",
)
replace(
    "src/subcommand.rs",
    "        Response::Signal(received.as_str().into())\n      }",
    "        Response::Signal(received.as_str().into())\n      }\n      #[cfg(target_os = \"wasi\")]\n      Request::Signal => Response::Signal(String::from(\"unsupported\")),",
)
