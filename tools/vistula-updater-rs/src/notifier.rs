mod cinnamon;
mod commands;
mod config;
mod i18n;

use anyhow::Result;
use std::time::Duration;
use tokio::time::sleep;

/// Background notifier that checks for system updates periodically
#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt::init();

    let args: Vec<String> = std::env::args().collect();
    
    if args.len() > 1 && args[1] == "once" {
        check_updates_once().await?;
    } else {
        check_updates_loop().await?;
    }

    Ok(())
}

/// Check updates once and exit
async fn check_updates_once() -> Result<()> {
    if !commands::have_command("checkupdates") {
        eprintln!("Error: checkupdates not found. Install: pacman-contrib");
        return Ok(());
    }

    match commands::run_command("checkupdates", &[], false) {
        Ok(result) => {
            if !result.stdout.is_empty() {
                let count = result.stdout.lines().count();
                show_notification(&format!(
                    "{}: {}",
                    i18n::t("notify.title"),
                    count
                ));
            }
        }
        Err(e) => eprintln!("Failed to check updates: {}", e),
    }

    Ok(())
}

/// Check updates periodically (every hour)
async fn check_updates_loop() -> Result<()> {
    loop {
        check_updates_once().await?;
        sleep(Duration::from_secs(3600)).await;
    }
}

/// Show system notification using notify-send
fn show_notification(message: &str) {
    let _ = std::process::Command::new("notify-send")
        .args(&["--urgency=normal", "VistulaOS Updater", message])
        .output();
}
