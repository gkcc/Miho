use std::{env, fs, path::PathBuf};

use miho_core::{
    contract::Game,
    output::ArtifactBundle,
    workbook::{build_workbook_bytes, workbook_source_paths},
};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut arguments = env::args_os().skip(1);
    let game = match arguments.next().and_then(|value| value.into_string().ok()) {
        Some(value) if value == "hsr" => Game::Hsr,
        Some(value) if value == "zzz" => Game::Zzz,
        _ => return Err("usage: workbook_contract <hsr|zzz> <csv-dir> <output.xlsx>".into()),
    };
    let input = arguments
        .next()
        .map(PathBuf::from)
        .ok_or("missing CSV directory")?;
    let output = arguments
        .next()
        .map(PathBuf::from)
        .ok_or("missing output path")?;
    if arguments.next().is_some() {
        return Err("too many arguments".into());
    }

    let mut bundle = ArtifactBundle::default();
    for relative in workbook_source_paths(game) {
        bundle.add_bytes(relative, fs::read(input.join(relative))?)?;
    }
    fs::write(output, build_workbook_bytes(game, &bundle)?)?;
    Ok(())
}
