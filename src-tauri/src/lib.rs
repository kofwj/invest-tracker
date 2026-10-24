use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::{Manager, RunEvent, WindowEvent};

#[allow(dead_code)]
struct BackendState {
    child: Arc<Mutex<Option<Child>>>,
    port: u16,
}


/// 发送轻量 HTTP GET 请求探测 /api/health，不需要引入第三方 HTTP 客户端 crate
fn check_health(port: u16) -> bool {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    if let Ok(mut stream) = TcpStream::connect_timeout(&addr, Duration::from_millis(300)) {
        let _ = stream.set_read_timeout(Some(Duration::from_millis(600)));
        let _ = stream.set_write_timeout(Some(Duration::from_millis(600)));
        let req = format!(
            "GET /api/health HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nConnection: close\r\n\r\n",
            port
        );
        if stream.write_all(req.as_bytes()).is_ok() {
            let mut buf = [0u8; 1024];
            if let Ok(n) = stream.read(&mut buf) {
                let resp = String::from_utf8_lossy(&buf[..n]);
                return resp.contains("200 OK") && resp.contains("\"status\":\"ok\"");
            }
        }
    }
    false
}

/// 检测端口是否可绑定
fn is_port_available(port: u16) -> bool {
    TcpListener::bind(("127.0.0.1", port)).is_ok()
}

/// 找到可用端口（默认优先 8000）
fn resolve_port() -> u16 {
    if let Ok(env_port) = std::env::var("PORT") {
        if let Ok(p) = env_port.trim().parse::<u16>() {
            return p;
        }
    }
    if check_health(8000) || is_port_available(8000) {
        return 8000;
    }
    for p in 8001..8100 {
        if is_port_available(p) {
            return p;
        }
    }
    8000
}

/// 寻找后端可执行文件或入口
fn resolve_backend_cmd() -> (String, Vec<String>, Option<PathBuf>) {
    // 1. 显式环境变量
    if let Ok(bin) = std::env::var("INVEST_TRACKER_BACKEND_BIN") {
        let p = PathBuf::from(bin.trim());
        if p.exists() {
            return (p.to_string_lossy().to_string(), vec![], p.parent().map(|d| d.to_path_buf()));
        }
    }

    // 2. macOS .app 打包目录或可执行文件同级目录
    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            let sidecar_candidates = [
                exe_dir.join("invest-tracker-backend"),
                exe_dir.join("binaries/invest-tracker-backend-aarch64-apple-darwin"),
                exe_dir.join("binaries/invest-tracker-backend-x86_64-apple-darwin"),
                exe_dir.join("binaries/invest-tracker-backend"),
            ];
            for candidate in &sidecar_candidates {
                if candidate.is_file() {
                    return (
                        candidate.to_string_lossy().to_string(),
                        vec![],
                        candidate.parent().map(|d| d.to_path_buf()),
                    );
                }
            }
        }
    }

    // 3. 项目工作区目录（开发模式下运行）
    let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let candidates = [
        cwd.join("src-tauri/binaries/invest-tracker-backend-aarch64-apple-darwin"),
        cwd.join("src-tauri/binaries/invest-tracker-backend"),
        cwd.join("binaries/invest-tracker-backend-aarch64-apple-darwin"),
        cwd.join("dist/invest-tracker-backend/invest-tracker-backend"),
    ];
    for candidate in &candidates {
        if candidate.is_file() {
            return (
                candidate.to_string_lossy().to_string(),
                vec![],
                candidate.parent().map(|d| d.to_path_buf()),
            );
        }
    }

    // 4. 开发回落：Python 源码运行 backend/main.py
    let root = if cwd.join("backend/main.py").exists() {
        cwd.clone()
    } else if cwd.parent().map(|p| p.join("backend/main.py").exists()).unwrap_or(false) {
        cwd.parent().unwrap().to_path_buf()
    } else {
        cwd.clone()
    };

    let python_candidates = [
        std::env::var("PYTHON_BIN").ok().map(PathBuf::from),
        Some(root.join(".venv/bin/python")),
        Some(root.join("venv/bin/python")),
        Some(PathBuf::from("python3")),
    ];

    for py_opt in python_candidates.into_iter().flatten() {
        let script = root.join("backend/main.py");
        if script.exists() {
            return (
                py_opt.to_string_lossy().to_string(),
                vec![script.to_string_lossy().to_string()],
                Some(root.clone()),
            );
        }
    }

    ("invest-tracker-backend".to_string(), vec![], None)
}

/// 优雅终止后端子进程
fn terminate_child(child_arc: &Arc<Mutex<Option<Child>>>) {
    let mut guard = match child_arc.lock() {
        Ok(g) => g,
        Err(poisoned) => poisoned.into_inner(),
    };
    if let Some(mut child) = guard.take() {
        log::info!("正在停止后端子进程 (PID: {})...", child.id());
        #[cfg(unix)]
        {
            let pid = child.id() as i32;
            unsafe {
                libc::kill(pid, libc::SIGTERM);
            }
            let start = Instant::now();
            while start.elapsed() < Duration::from_millis(2000) {
                if let Ok(Some(_)) = child.try_wait() {
                    log::info!("后端子进程已平稳退出。");
                    return;
                }
                std::thread::sleep(Duration::from_millis(50));
            }
        }
        log::warn!("后端子进程超时未退出，发送强制终止信号...");
        let _ = child.kill();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let child_holder: Arc<Mutex<Option<Child>>> = Arc::new(Mutex::new(None));
    let child_for_setup = Arc::clone(&child_holder);
    let child_for_exit = Arc::clone(&child_holder);
    let port = resolve_port();

    tauri::Builder::default()
        .manage(BackendState {
            child: Arc::clone(&child_holder),
            port,
        })
        .setup(move |app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // 检查该端口是否已有存活的后端
            if check_health(port) {
                log::info!("检测到端口 {} 已有存活的投资看板后端，复用该服务。", port);
            } else {
                let (cmd_bin, args, cwd_opt) = resolve_backend_cmd();
                log::info!("正在启动后端子进程: {} {:?} (端口: {})", cmd_bin, args, port);

                let mut cmd = Command::new(&cmd_bin);
                cmd.args(&args)
                    .env("PORT", port.to_string())
                    .env("HOST", "127.0.0.1")
                    .env("INVEST_TRACKER_NO_BROWSER", "1")
                    .stdout(Stdio::inherit())
                    .stderr(Stdio::inherit());

                if let Some(ref cwd) = cwd_opt {
                    cmd.current_dir(cwd);
                }

                // Tauri 打包后前端产物落在 .app/Contents/Resources/frontend/dist，
                // 侧车只在自己所在目录找，找不到就退化成纯 API（窗口打开是 404）。
                // 这里显式指路；开发模式下该目录不存在，留给后端按仓库路径自己找。
                if let Ok(resource_dir) = app.path().resource_dir() {
                    let dist = resource_dir.join("frontend").join("dist");
                    if dist.is_dir() {
                        cmd.env("FRONTEND_DIST", &dist);
                    }
                }

                match cmd.spawn() {
                    Ok(child) => {
                        log::info!("后端子进程已拉起，PID: {}", child.id());
                        if let Ok(mut g) = child_for_setup.lock() {
                            *g = Some(child);
                        }
                    }
                    Err(err) => {
                        log::error!("拉起后端子进程失败: {} (尝试执行: {})", err, cmd_bin);
                    }
                }
            }

            // 在后台等待后端 /api/health 就绪并导航主窗口
            let app_handle = app.handle().clone();
            std::thread::spawn(move || {
                let deadline = Instant::now() + Duration::from_secs(20);
                let mut ready = false;
                while Instant::now() < deadline {
                    if check_health(port) {
                        ready = true;
                        break;
                    }
                    std::thread::sleep(Duration::from_millis(150));
                }

                if ready {
                    let target_url = format!("http://127.0.0.1:{}", port);
                    log::info!("后端已就绪，主窗口加载目标地址: {}", target_url);
                    if let Some(window) = app_handle.get_webview_window("main") {
                        let eval_script = format!("window.location.replace('{}');", target_url);
                        let _ = window.eval(&eval_script);
                    }
                } else {
                    log::error!("后端在 20 秒内未响应 /api/health！");
                }
            });

            Ok(())
        })
        .on_window_event({
            let child_for_window = Arc::clone(&child_holder);
            move |_window, event| {
                if let WindowEvent::Destroyed = event {
                    terminate_child(&child_for_window);
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(move |_app_handle, event| {
            if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
                terminate_child(&child_for_exit);
            }
        });
}

