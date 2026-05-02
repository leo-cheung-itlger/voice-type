#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::env;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use tauri::{
    Emitter,
    menu::{MenuBuilder, MenuItemBuilder},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, WindowEvent,
};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

#[derive(Clone, serde::Serialize)]
struct SingleInstancePayload {
    args: Vec<String>,
    cwd: String,
}

fn project_root() -> PathBuf {
    if let Ok(root) = env::var("VOICETYPE_ROOT") {
        let path = PathBuf::from(root);
        if path.join("scripts\\start-runtime.ps1").exists() {
            return path;
        }
    }
    if let Ok(exe) = env::current_exe() {
        if let Some(root) = find_project_root_near(exe.parent()) {
            return root;
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|path| path.parent())
        .expect("src-tauri should live under frontend")
        .to_path_buf()
}

fn find_project_root_near(start: Option<&Path>) -> Option<PathBuf> {
    let mut current = start?.to_path_buf();
    for _ in 0..6 {
        if current.join("scripts\\start-runtime.ps1").exists() && current.join("venv\\Scripts\\python.exe").exists() {
            return Some(current);
        }
        if !current.pop() {
            break;
        }
    }
    None
}

fn script_path(script: &str) -> PathBuf {
    project_root().join(script)
}

fn powershell_command(root: &PathBuf, script: &str) -> Command {
    let mut command = Command::new("powershell.exe");
    command
        .current_dir(root)
        .arg("-NoProfile")
        .arg("-ExecutionPolicy")
        .arg("Bypass")
        .arg("-File")
        .arg(root.join(script))
        .arg("-Root")
        .arg(root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    command.creation_flags(CREATE_NO_WINDOW);
    command
}

fn start_runtime() -> Result<String, String> {
    let root = project_root();
    let script = root.join("scripts\\start-runtime.ps1");
    let python = root.join("venv\\Scripts\\python.exe");
    if !script.exists() {
        return Err(format!("运行时脚本缺失: {}", script.display()));
    }
    if !python.exists() {
        return Err(format!("Python venv 缺失: {}", python.display()));
    }
    powershell_command(&root, "scripts\\start-runtime.ps1")
        .spawn()
        .map(|_| "runtime starting".to_string())
        .map_err(|err| format!("启动运行时失败: {err}"))
}

fn stop_runtime() -> Result<String, String> {
    let root = project_root();
    let script = script_path("scripts\\stop-dev.ps1");
    if !script.exists() {
        return Err(format!("停止脚本缺失: {}", script.display()));
    }
    let status = powershell_command(&root, "scripts\\stop-dev.ps1")
        .status()
        .map_err(|err| format!("停止运行时失败: {err}"))?;
    if status.success() {
        Ok("runtime stopped".to_string())
    } else {
        Err(format!("停止运行时失败，退出码: {status}"))
    }
}

#[tauri::command]
fn runtime_diagnostics() -> Result<String, String> {
    let root = project_root();
    let start_script = root.join("scripts\\start-runtime.ps1");
    let stop_script = root.join("scripts\\stop-dev.ps1");
    let python = root.join("venv\\Scripts\\python.exe");
    Ok(format!(
        "root={}\nstart_runtime={}\nstop_runtime={}\npython={}\napi=http://127.0.0.1:55342/api",
        root.display(),
        start_script.exists(),
        stop_script.exists(),
        python.exists()
    ))
}

#[tauri::command]
fn restart_runtime() -> Result<String, String> {
    let _ = stop_runtime();
    start_runtime()
}

fn show_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, argv, cwd| {
            show_main_window(app);
            let _ = app.emit("single-instance", SingleInstancePayload { args: argv, cwd });
            let _ = app.emit("runtime-toast", "VoiceType 已在运行，已切换到当前窗口。");
        }))
        .invoke_handler(tauri::generate_handler![runtime_diagnostics, restart_runtime])
        .setup(|app| {
            if let Err(message) = start_runtime() {
                let _ = app.emit("runtime-toast", message);
            }

            let show = MenuItemBuilder::with_id("show", "Show VoiceType").build(app)?;
            let quit = MenuItemBuilder::with_id("quit", "Quit").build(app)?;
            let menu = MenuBuilder::new(app).items(&[&show, &quit]).build()?;

            let mut tray = TrayIconBuilder::new()
                .menu(&menu)
                .show_menu_on_left_click(false);
            if let Some(icon) = app.default_window_icon() {
                tray = tray.icon(icon.clone());
            }

            tray.on_menu_event(|app, event| match event.id().as_ref() {
                    "show" => show_main_window(app),
                    "quit" => {
                        let _ = stop_runtime();
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        show_main_window(tray.app_handle());
                    }
                })
                .build(app)?;

            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building VoiceType desktop app")
        .run(|_app, event| {
            if let tauri::RunEvent::Exit = event {
                let _ = stop_runtime();
            }
        });
}
