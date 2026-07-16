#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

#[cfg(all(not(debug_assertions), not(feature = "custom-protocol")))]
compile_error!("release miho-desktop.exe requires the custom-protocol feature");

fn main() {
    miho_desktop_lib::run();
}
