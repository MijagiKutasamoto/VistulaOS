use once_cell::sync::Lazy;
use serde_json::{Map, Value};
use std::collections::HashMap;
use std::env;
use std::path::PathBuf;
use std::sync::Mutex;

type Translations = HashMap<String, String>;

static LANGUAGE: Lazy<Mutex<String>> = Lazy::new(|| Mutex::new(detect_language()));
static CACHE: Lazy<Mutex<HashMap<String, Translations>>> = Lazy::new(|| Mutex::new(HashMap::new()));

/// Detect system language from environment variables
fn detect_language() -> String {
    // Check for explicit override
    if let Ok(lang) = env::var("VISTULA_LANG") {
        return normalize_lang(&lang);
    }

    // Check standard locale variables
    for var in &["LC_ALL", "LC_MESSAGES", "LANG"] {
        if let Ok(value) = env::var(var) {
            return normalize_lang(&value);
        }
    }

    String::from("en")
}

/// Normalize language code (pl_PL.UTF-8 -> pl)
fn normalize_lang(lang: &str) -> String {
    let lang = lang.trim().to_lowercase();

    if lang.is_empty() {
        return String::from("en");
    }

    let lang = lang.split('.').next().unwrap_or(&lang);
    let lang = lang.split('@').next().unwrap_or(lang);
    let lang = lang.split('_').next().unwrap_or(lang);

    if lang == "pl" || lang == "en" {
        lang.to_string()
    } else {
        String::from("en")
    }
}

/// Load translations from JSON file
fn load_translations(lang: &str) -> anyhow::Result<Translations> {
    let mut cache = CACHE.lock().unwrap();
    if let Some(trans) = cache.get(lang) {
        return Ok(trans.clone());
    }

    let assets_path = get_assets_path();
    let file_path = assets_path.join("i18n").join(format!("{}.json", lang));

    let content = std::fs::read_to_string(&file_path)
        .unwrap_or_else(|_| String::from("{}"));

    let json: Map<String, Value> = serde_json::from_str(&content)
        .unwrap_or_default();

    let mut translations = Translations::new();
    for (key, value) in json {
        if let Some(text) = value.as_str() {
            translations.insert(key, text.to_string());
        }
    }

    cache.insert(lang.to_string(), translations.clone());
    Ok(translations)
}

/// Get assets directory path
fn get_assets_path() -> PathBuf {
    // Override via environment variable
    if let Ok(path) = env::var("VISTULA_UPDATER_ASSETS") {
        return PathBuf::from(path);
    }

    // Development mode: assets are in the workspace
    let current_exe = std::env::current_exe().ok();
    if let Some(exe) = current_exe {
        if let Some(parent) = exe.parent() {
            if let Some(grandparent) = parent.parent() {
                let assets = grandparent.join("assets");
                if assets.exists() {
                    return assets;
                }
            }
        }
    }

    // Fallback: expect assets in current directory
    PathBuf::from("assets")
}

/// Set current language
pub fn set_language(lang: &str) {
    let normalized = normalize_lang(lang);
    let mut current = LANGUAGE.lock().unwrap();
    *current = normalized;
}

/// Get current language
pub fn current_language() -> String {
    LANGUAGE.lock().unwrap().clone()
}

/// Translate a message key
pub fn t(key: &str) -> String {
    t_with_args(key, &HashMap::new())
}

/// Translate with argument substitution
pub fn t_with_args(key: &str, args: &HashMap<&str, String>) -> String {
    let lang = current_language();
    let text = load_translations(&lang)
        .ok()
        .and_then(|trans| trans.get(key).cloned())
        .or_else(|| {
            load_translations("en")
                .ok()
                .and_then(|trans| trans.get(key).cloned())
        })
        .unwrap_or_else(|| key.to_string());

    if args.is_empty() {
        text
    } else {
        // Simple string substitution: {key} -> value
        let mut result = text;
        for (k, v) in args {
            result = result.replace(&format!("{{{}}}", k), v);
        }
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normalize_lang() {
        assert_eq!(normalize_lang("pl"), "pl");
        assert_eq!(normalize_lang("pl_PL"), "pl");
        assert_eq!(normalize_lang("pl_PL.UTF-8"), "pl");
        assert_eq!(normalize_lang("en_US.utf8@variant"), "en");
        assert_eq!(normalize_lang("de"), "en"); // fallback for unknown
    }

    #[test]
    fn test_translate() {
        set_language("en");
        let text = t("app.title");
        assert!(!text.is_empty());
        assert_eq!(text, "VistulaOS Updater");
    }

    #[test]
    fn test_translate_with_args() {
        set_language("en");
        let mut args = HashMap::new();
        args.insert("n", "5".to_string());
        let text = t_with_args("notify.updates_available", &args);
        assert!(text.contains("5"));
    }
}
