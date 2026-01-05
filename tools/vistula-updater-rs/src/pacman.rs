/// Represents an available system update
#[derive(Debug, Clone)]
pub struct PackageUpdate {
    pub name: String,
    pub current_version: String,
    pub new_version: String,
}

/// Parse checkupdates output into structured updates
pub fn parse_updates(output: &str) -> Vec<PackageUpdate> {
    output
        .lines()
        .filter(|line| !line.trim().is_empty() && !line.starts_with("::"))
        .filter_map(|line| {
            let parts: Vec<&str> = line.split_whitespace().collect();
            if parts.len() >= 4 && parts[2] == "->" {
                Some(PackageUpdate {
                    name: parts[0].to_string(),
                    current_version: parts[1].to_string(),
                    new_version: parts[3].to_string(),
                })
            } else {
                None
            }
        })
        .collect()
}

/// Check for system updates using checkupdates
pub async fn check_for_updates() -> Result<Vec<PackageUpdate>, String> {
    let result = crate::commands::run_command("checkupdates", &[], false)
        .map_err(|e| e.to_string())?;
    Ok(parse_updates(&result.stdout))
}

/// Update system using pacman with elevation
pub async fn update_system() -> Result<(), String> {
    crate::commands::run_command("pacman", &["-Syu"], true)
        .map_err(|e| e.to_string())?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_updates() {
        let output = "package1 1.0.0 -> 1.0.1\npackage2 2.0 -> 2.1.0\n";
        let updates = parse_updates(output);
        
        assert_eq!(updates.len(), 2);
        assert_eq!(updates[0].name, "package1");
        assert_eq!(updates[0].current_version, "1.0.0");
        assert_eq!(updates[0].new_version, "1.0.1");
    }

    #[test]
    fn test_parse_updates_with_empty_lines() {
        let output = "pkg1 1.0 -> 1.1\n\n:: Some header\npkg2 2.0 -> 2.1\n";
        let updates = parse_updates(output);
        
        assert_eq!(updates.len(), 2);
    }
    
    #[test]
    fn test_parse_updates_empty() {
        let output = "";
        let updates = parse_updates(output);
        assert_eq!(updates.len(), 0);
    }
    
    #[test]
    fn test_parse_updates_only_headers() {
        let output = ":: Package upgrades\n:: Some header\n";
        let updates = parse_updates(output);
        assert_eq!(updates.len(), 0);
    }
    
    #[test]
    fn test_package_update_creation() {
        let update = PackageUpdate {
            name: "test".to_string(),
            current_version: "1.0".to_string(),
            new_version: "2.0".to_string(),
        };
        assert_eq!(update.name, "test");
        assert_eq!(update.current_version, "1.0");
        assert_eq!(update.new_version, "2.0");
    }
}
