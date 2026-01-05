use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FlatpakApp {
    pub appid: String,
    pub name: String,
    pub origin: String,
    pub version: Option<String>,
}

#[derive(Debug, Clone)]
pub struct FlatpakRemote {
    pub name: String,
    pub url: String,
    pub is_default: bool,
}

/// Parse flatpak list output
pub fn parse_flatpak_list(output: &str) -> Vec<FlatpakApp> {
    output
        .lines()
        .skip(1) // Skip header line
        .filter(|line| !line.trim().is_empty())
        .filter_map(|line| {
            let parts: Vec<&str> = line.split_whitespace().collect();
            if parts.len() >= 3 {
                Some(FlatpakApp {
                    appid: parts[0].to_string(),
                    name: parts[1].to_string(),
                    origin: parts[2].to_string(),
                    version: parts.get(3).map(|v| v.to_string()),
                })
            } else {
                None
            }
        })
        .collect()
}

/// Get installed flatpak applications
pub async fn list_installed() -> Result<Vec<FlatpakApp>, String> {
    let result = crate::commands::run_command(
        "flatpak",
        &["list", "--app", "--columns=application,name,origin"],
        false,
    ).map_err(|e| e.to_string())?;
    Ok(parse_flatpak_list(&result.stdout))
}

/// Search flatpak applications by query
pub async fn search(query: &str, _remote: &str) -> Result<Vec<FlatpakApp>, String> {
    let result = crate::commands::run_command(
        "flatpak",
        &["search", "--columns=id,name,default-branch", query],
        false,
    ).map_err(|e| e.to_string())?;
    Ok(parse_flatpak_list(&result.stdout))
}

/// Install a flatpak application
pub async fn install(appid: &str) -> Result<(), String> {
    crate::commands::run_command("flatpak", &["install", appid], true)
        .map_err(|e| e.to_string())?;
    Ok(())
}

/// Uninstall a flatpak application
pub async fn uninstall(appid: &str) -> Result<(), String> {
    crate::commands::run_command("flatpak", &["uninstall", appid], true)
        .map_err(|e| e.to_string())?;
    Ok(())
}

/// Update all installed flatpak applications
pub async fn update_all() -> Result<(), String> {
    crate::commands::run_command("flatpak", &["update"], true)
        .map_err(|e| e.to_string())?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_flatpak_list() {
        let output = "Application\tName\tOrigin\n\
                      org.gnome.Gedit\tText Editor\tflathub\n\
                      org.blender.Blender\tBlender\tflathub\n";
        let apps = parse_flatpak_list(output);
        
        assert_eq!(apps.len(), 2);
        assert_eq!(apps[0].appid, "org.gnome.Gedit");
        assert_eq!(apps[0].name, "Text");
    }
    
    #[test]
    fn test_parse_flatpak_list_empty() {
        let output = "Application\tName\tOrigin\n";
        let apps = parse_flatpak_list(output);
        assert_eq!(apps.len(), 0);
    }
    
    #[test]
    fn test_flatpak_app_creation() {
        let app = FlatpakApp {
            appid: "org.test.App".to_string(),
            name: "Test App".to_string(),
            origin: "flathub".to_string(),
            version: Some("1.0.0".to_string()),
        };
        assert_eq!(app.appid, "org.test.App");
        assert_eq!(app.version, Some("1.0.0".to_string()));
    }
}
