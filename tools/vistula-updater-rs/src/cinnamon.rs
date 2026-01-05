use std::process::Command;

/// Try to read GTK theme from Cinnamon settings
pub fn read_cinnamon_theme() -> Option<String> {
    let output = Command::new("gsettings")
        .args(&["get", "org.cinnamon.desktop.interface", "gtk-theme"])
        .output()
        .ok()?;

    if !output.status.success() {
        return None;
    }

    let theme = String::from_utf8_lossy(&output.stdout);
    // Remove quotes from output: 'Theme-Name' -> Theme-Name
    let theme = theme.trim().trim_matches('\'').to_string();

    if theme.is_empty() {
        None
    } else {
        Some(theme)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_read_cinnamon_theme() {
        // This test may pass or fail depending on whether Cinnamon is installed
        // It's mainly for checking that the function doesn't panic
        let _ = read_cinnamon_theme();
    }
}
