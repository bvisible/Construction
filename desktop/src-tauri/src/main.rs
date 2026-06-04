// OpenConstructionERP Desktop, Tauri v2 application.
//
// Manages the FastAPI backend as a sidecar process.
// The React frontend loads in a native webview window.
// Backend communicates via http://localhost:{port}/api/

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::Mutex;
use tauri::{
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, RunEvent,
};
use tauri_plugin_shell::ShellExt;

struct AppState {
    backend_running: Mutex<bool>,
}

/// Find an available port for the backend server.
fn find_available_port() -> u16 {
    portpicker::pick_unused_port().expect("No available port found")
}

/// Wait for the backend health endpoint to respond.
///
/// Polls `/api/health` every ~500ms until it succeeds or the timeout elapses.
/// While waiting, updates the splash screen ("main" window) so the user sees
/// progress: after ~8 seconds still waiting, the status line is updated to
/// reassure the user that first-run database setup is in progress.
async fn wait_for_backend(handle: &tauri::AppHandle, port: u16, timeout_secs: u64) -> bool {
    let client = reqwest::Client::new();
    let url = format!("http://127.0.0.1:{}/api/health", port);
    let start = std::time::Instant::now();
    let mut progress_shown = false;

    while start.elapsed().as_secs() < timeout_secs {
        if let Ok(resp) = client.get(&url).send().await {
            if resp.status().is_success() {
                return true;
            }
        }

        // After ~8 seconds still waiting, nudge the splash status so the user
        // knows the (potentially slow) first-run database setup is underway.
        if !progress_shown && start.elapsed().as_secs() >= 8 {
            progress_shown = true;
            if let Some(window) = handle.get_webview_window("main") {
                let _ = window.eval("setStatus('Setting up the local database, almost there')");
            }
        }

        tokio::time::sleep(std::time::Duration::from_millis(500)).await;
    }
    false
}

fn main() {
    let port = find_available_port();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .manage(AppState {
            backend_running: Mutex::new(false),
        })
        .setup(move |app| {
            let handle = app.handle().clone();

            // Build tray icon
            let _tray = TrayIconBuilder::new()
                .tooltip("OpenConstructionERP")
                .on_tray_icon_event(move |tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        // Show/focus main window on tray click
                        if let Some(window) = tray.app_handle().get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                })
                .build(app)?;

            // Start the backend sidecar.
            //
            // The "serve" subcommand is required: the CLI only accepts --host /
            // --port under a subcommand. Invoked bare it would ignore them,
            // fall back to defaults, and on first run block on an interactive
            // "open in browser?" stdin prompt that a sidecar has no terminal
            // for. With --data-dir left unset the sidecar uses its default
            // (~/.openestimate), which stays writable even for a per-machine
            // install under Program Files.
            let shell = handle.shell();
            let sidecar_cmd = shell
                .sidecar("openestimate-server")
                .expect("Failed to create sidecar command")
                .args(["serve", "--host", "127.0.0.1", "--port", &port.to_string()]);

            let (mut _rx, _child) = sidecar_cmd
                .spawn()
                .expect("Failed to spawn backend sidecar");

            // Mark backend as running
            let state = handle.state::<AppState>();
            *state.backend_running.lock().unwrap() = true;

            // Wait for backend to be ready, then navigate the webview from the
            // splash screen to the live application. First-run initialization of
            // the embedded PostgreSQL database can take a while, so allow up to
            // 150 seconds before giving up.
            let handle_clone = handle.clone();
            tauri::async_runtime::spawn(async move {
                if wait_for_backend(&handle_clone, port, 150).await {
                    if let Some(window) = handle_clone.get_webview_window("main") {
                        let url = format!("http://127.0.0.1:{}/", port);
                        // The window is visible by default; show + focus defensively.
                        let _ = window.show();
                        let _ = window.set_focus();
                        let _ = window.eval(&format!("window.location.replace('{}')", url));
                    }
                } else {
                    eprintln!("Backend failed to start within 150 seconds");
                    if let Some(window) = handle_clone.get_webview_window("main") {
                        let _ = window.eval(
                            "setError('The application backend did not start in time. \
Please close this window and try again. If the problem persists, contact \
info@datadrivenconstruction.io')",
                        );
                    }
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("Error building Tauri application")
        .run(|_app, event| {
            if let RunEvent::ExitRequested { .. } = event {
                // Backend sidecar is automatically killed when the app exits
            }
        });
}
