use anyhow::Context;
use std::process::{Command, Stdio};
use anyhow::Result;
use tokio::io::AsyncBufReadExt;
use tokio::process::Command as TokioCommand;

/// Check if a command/binary exists in PATH
pub fn have_command(name: &str) -> bool {
    which::which(name).is_ok()
}

/// Result of command execution
#[derive(Debug, Clone)]
pub struct CommandResult {
    pub exit_code: i32,
    pub stdout: String,
    pub stderr: String,
}

impl CommandResult {
    pub fn success(&self) -> bool {
        self.exit_code == 0
    }
}

/// Run command synchronously with optional privilege escalation
pub fn run_command(
    cmd: &str,
    args: &[&str],
    use_pkexec: bool,
) -> Result<CommandResult> {
    let actual_cmd = if use_pkexec { "pkexec" } else { cmd };
    let actual_args: Vec<&str> = if use_pkexec {
        vec![cmd].into_iter().chain(args.iter().copied()).collect()
    } else {
        args.to_vec()
    };

    let output = Command::new(actual_cmd)
        .args(&actual_args)
        .output()
        .with_context(|| format!("Failed to execute: {} {:?}", actual_cmd, actual_args))?;

    Ok(CommandResult {
        exit_code: output.status.code().unwrap_or(-1),
        stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
        stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
    })
}

/// Run command asynchronously with callbacks
pub async fn run_command_async<F, G>(
    cmd: &str,
    args: &[&str],
    use_pkexec: bool,
    mut on_line: Option<F>,
    on_done: G,
) -> Result<()>
where
    F: FnMut(String) + Send + 'static,
    G: FnOnce(CommandResult) + Send + 'static,
{
    let actual_cmd = if use_pkexec { "pkexec" } else { cmd };
    let actual_args: Vec<String> = if use_pkexec {
        vec![cmd.to_string()]
            .into_iter()
            .chain(args.iter().map(|s| s.to_string()))
            .collect()
    } else {
        args.iter().map(|s| s.to_string()).collect()
    };

    let mut child = TokioCommand::new(actual_cmd)
        .args(&actual_args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .with_context(|| format!("Failed to spawn: {} {:?}", actual_cmd, actual_args))?;

    let stdout = child
        .stdout
        .take()
        .context("Failed to capture stdout")?;
    let stderr = child
        .stderr
        .take()
        .context("Failed to capture stderr")?;

    let mut stdout_reader = tokio::io::BufReader::new(stdout).lines();
    let mut stderr_reader = tokio::io::BufReader::new(stderr).lines();

    let mut stdout_buf = String::new();
    let mut stderr_buf = String::new();

    // Read output lines
    tokio::select! {
        _ = async {
            while let Ok(Some(line)) = stdout_reader.next_line().await {
                if let Some(ref mut cb) = on_line {
                    cb(line.clone());
                }
                stdout_buf.push_str(&line);
                stdout_buf.push('\n');
            }
        } => {}
        _ = async {
            while let Ok(Some(line)) = stderr_reader.next_line().await {
                stderr_buf.push_str(&line);
                stderr_buf.push('\n');
            }
        } => {}
    }

    let status = child
        .wait()
        .await
        .context("Failed to wait for command")?;

    let result = CommandResult {
        exit_code: status.code().unwrap_or(-1),
        stdout: stdout_buf,
        stderr: stderr_buf,
    };

    on_done(result);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_have_command() {
        assert!(have_command("ls"));
        assert!(!have_command("nonexistent_command_xyz"));
    }

    #[test]
    fn test_run_command() {
        let result = run_command("echo", &["hello"], false).unwrap();
        assert!(result.success());
        assert!(result.stdout.contains("hello"));
    }
}
