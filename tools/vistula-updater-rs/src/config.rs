use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppConfig {
    pub language: String,
    pub theme: String,
    pub categories: HashMap<String, Vec<String>>,
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            language: "en".to_string(),
            theme: "auto".to_string(),
            categories: HashMap::new(),
        }
    }
}

/// Get config directory path (~/.config/vistula-updater)
fn get_config_dir() -> PathBuf {
    if let Ok(home) = std::env::var("HOME") {
        PathBuf::from(home).join(".config").join("vistula-updater")
    } else {
        PathBuf::from(".config/vistula-updater")
    }
}

/// Load configuration from file
pub fn load_config() -> anyhow::Result<AppConfig> {
    let config_dir = get_config_dir();
    let config_file = config_dir.join("config.json");

    if !config_file.exists() {
        return Ok(AppConfig::default());
    }

    let content = std::fs::read_to_string(&config_file)?;
    let config = serde_json::from_str(&content)?;
    Ok(config)
}

/// Save configuration to file
pub fn save_config(config: &AppConfig) -> anyhow::Result<()> {
    let config_dir = get_config_dir();
    std::fs::create_dir_all(&config_dir)?;

    let config_file = config_dir.join("config.json");
    let content = serde_json::to_string_pretty(config)?;
    std::fs::write(&config_file, content)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        let config = AppConfig::default();
        assert_eq!(config.language, "en");
        assert_eq!(config.theme, "auto");
    }

    #[test]
    fn test_config_serialization() {
        let config = AppConfig::default();
        let json = serde_json::to_string(&config).unwrap();
        let deserialized: AppConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.language, config.language);
    }
}
