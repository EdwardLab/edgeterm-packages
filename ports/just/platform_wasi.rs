use super::*;

impl PlatformInterface for Platform {
  fn make_shebang_command(
    _config: &Config,
    path: &Path,
    _shebang: Shebang,
    working_directory: Option<&Path>,
  ) -> Result<Command, OutputError> {
    let mut command = Command::resolve(path);
    if let Some(working_directory) = working_directory {
      command.current_dir(working_directory);
    }
    Ok(command)
  }

  fn set_execute_permission(_path: &Path) -> io::Result<()> {
    Ok(())
  }

  fn signal_from_exit_status(_exit_status: ExitStatus) -> Option<i32> {
    None
  }

  fn convert_native_path(_config: &Config, _working_directory: &Path, path: &Path) -> StringResult {
    path
      .to_str()
      .map(str::to_string)
      .ok_or_else(|| String::from("Error getting current directory: unicode decode error"))
  }

  fn install_signal_handler<T: Fn(Signal) + Send + 'static>(_handler: T) -> RunResult<'static> {
    Ok(())
  }
}
