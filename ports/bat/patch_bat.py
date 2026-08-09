#!/usr/bin/env python3
from pathlib import Path
import sys


source = Path(sys.argv[1]) / "src/bin/bat/directories.rs"
text = source.read_text()
old = '''    fn new() -> Option<BatProjectDirs> {
        let basedirs = etcetera::choose_base_strategy().ok()?;

        // Checks whether or not `$BAT_CACHE_PATH` exists. If it doesn't, set the cache dir to our
        // system's default cache home.
        let cache_dir = if let Some(cache_dir) = env::var_os("BAT_CACHE_PATH").map(PathBuf::from) {
            cache_dir
        } else {
            basedirs.cache_dir().join("bat")
        };

        // Checks whether or not `$BAT_CONFIG_DIR` exists. If it doesn't, set the config dir to our
        // system's default configuration home.
        let config_dir = if let Some(config_dir) = env::var_os("BAT_CONFIG_DIR").map(PathBuf::from)
        {
            config_dir
        } else {
            basedirs.config_dir().join("bat")
        };
'''
new = '''    fn new() -> Option<BatProjectDirs> {
        let basedirs = etcetera::choose_base_strategy().ok();
        let home = env::var_os("HOME").map(PathBuf::from)?;

        // Checks whether or not `$BAT_CACHE_PATH` exists. If it doesn't, set the cache dir to our
        // system's default cache home.
        let cache_dir = if let Some(cache_dir) = env::var_os("BAT_CACHE_PATH").map(PathBuf::from) {
            cache_dir
        } else if let Some(ref basedirs) = basedirs {
            basedirs.cache_dir().join("bat")
        } else {
            home.join(".cache/bat")
        };

        // Checks whether or not `$BAT_CONFIG_DIR` exists. If it doesn't, set the config dir to our
        // system's default configuration home.
        let config_dir = if let Some(config_dir) = env::var_os("BAT_CONFIG_DIR").map(PathBuf::from)
        {
            config_dir
        } else if let Some(ref basedirs) = basedirs {
            basedirs.config_dir().join("bat")
        } else {
            home.join(".config/bat")
        };
'''
if old not in text:
    if new in text:
        raise SystemExit(0)
    raise SystemExit("bat project directory block was not found")
source.write_text(text.replace(old, new, 1))
