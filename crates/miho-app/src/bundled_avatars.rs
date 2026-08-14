//! Release-owned cold-start avatar seed.
//!
//! The visualizer only serves same-origin local images. These entries make a
//! clean install self-contained while still allowing unknown future slugs to
//! be retained from an existing output directory.

use miho_core::pipeline::Game;

pub(crate) type BundledAvatar = (&'static str, &'static [u8]);

static HSR_AVATARS: &[BundledAvatar] = &[
    (
        "acheron",
        include_bytes!("../assets/avatars/hsr/acheron.webp"),
    ),
    (
        "aglaea",
        include_bytes!("../assets/avatars/hsr/aglaea.webp"),
    ),
    ("anaxa", include_bytes!("../assets/avatars/hsr/anaxa.webp")),
    (
        "archer",
        include_bytes!("../assets/avatars/hsr/archer.webp"),
    ),
    (
        "argenti",
        include_bytes!("../assets/avatars/hsr/argenti.webp"),
    ),
    ("arlan", include_bytes!("../assets/avatars/hsr/arlan.webp")),
    (
        "ashveil",
        include_bytes!("../assets/avatars/hsr/ashveil.webp"),
    ),
    ("asta", include_bytes!("../assets/avatars/hsr/asta.webp")),
    (
        "aventurine-waveflair",
        include_bytes!("../assets/avatars/hsr/aventurine-waveflair.webp"),
    ),
    (
        "aventurine",
        include_bytes!("../assets/avatars/hsr/aventurine.webp"),
    ),
    ("bailu", include_bytes!("../assets/avatars/hsr/bailu.webp")),
    (
        "black-swan",
        include_bytes!("../assets/avatars/hsr/black-swan.webp"),
    ),
    ("blade", include_bytes!("../assets/avatars/hsr/blade.webp")),
    (
        "boothill",
        include_bytes!("../assets/avatars/hsr/boothill.webp"),
    ),
    (
        "bronya",
        include_bytes!("../assets/avatars/hsr/bronya.webp"),
    ),
    (
        "castorice",
        include_bytes!("../assets/avatars/hsr/castorice.webp"),
    ),
    (
        "cerydra",
        include_bytes!("../assets/avatars/hsr/cerydra.webp"),
    ),
    (
        "cipher",
        include_bytes!("../assets/avatars/hsr/cipher.webp"),
    ),
    ("clara", include_bytes!("../assets/avatars/hsr/clara.webp")),
    (
        "cyrene",
        include_bytes!("../assets/avatars/hsr/cyrene.webp"),
    ),
    (
        "dan-heng-imbibitor-lunae",
        include_bytes!("../assets/avatars/hsr/dan-heng-imbibitor-lunae.webp"),
    ),
    (
        "dan-heng-permansor-terrae",
        include_bytes!("../assets/avatars/hsr/dan-heng-permansor-terrae.webp"),
    ),
    (
        "dan-heng",
        include_bytes!("../assets/avatars/hsr/dan-heng.webp"),
    ),
    (
        "dr-ratio",
        include_bytes!("../assets/avatars/hsr/dr-ratio.webp"),
    ),
    (
        "evanescia",
        include_bytes!("../assets/avatars/hsr/evanescia.webp"),
    ),
    (
        "evernight",
        include_bytes!("../assets/avatars/hsr/evernight.webp"),
    ),
    (
        "feixiao",
        include_bytes!("../assets/avatars/hsr/feixiao.webp"),
    ),
    (
        "firefly",
        include_bytes!("../assets/avatars/hsr/firefly.webp"),
    ),
    (
        "fu-xuan",
        include_bytes!("../assets/avatars/hsr/fu-xuan.webp"),
    ),
    ("fugue", include_bytes!("../assets/avatars/hsr/fugue.webp")),
    (
        "gallagher",
        include_bytes!("../assets/avatars/hsr/gallagher.webp"),
    ),
    (
        "gepard",
        include_bytes!("../assets/avatars/hsr/gepard.webp"),
    ),
    (
        "gilgamesh",
        include_bytes!("../assets/avatars/hsr/gilgamesh.webp"),
    ),
    (
        "guinaifen",
        include_bytes!("../assets/avatars/hsr/guinaifen.webp"),
    ),
    ("hanya", include_bytes!("../assets/avatars/hsr/hanya.webp")),
    ("herta", include_bytes!("../assets/avatars/hsr/herta.webp")),
    (
        "himeko-nova",
        include_bytes!("../assets/avatars/hsr/himeko-nova.webp"),
    ),
    (
        "himeko",
        include_bytes!("../assets/avatars/hsr/himeko.webp"),
    ),
    ("hook", include_bytes!("../assets/avatars/hsr/hook.webp")),
    (
        "huohuo",
        include_bytes!("../assets/avatars/hsr/huohuo.webp"),
    ),
    (
        "hyacine",
        include_bytes!("../assets/avatars/hsr/hyacine.webp"),
    ),
    (
        "hysilens",
        include_bytes!("../assets/avatars/hsr/hysilens.webp"),
    ),
    ("jade", include_bytes!("../assets/avatars/hsr/jade.webp")),
    (
        "jiaoqiu",
        include_bytes!("../assets/avatars/hsr/jiaoqiu.webp"),
    ),
    (
        "jing-yuan",
        include_bytes!("../assets/avatars/hsr/jing-yuan.webp"),
    ),
    (
        "jingliu",
        include_bytes!("../assets/avatars/hsr/jingliu.webp"),
    ),
    ("kafka", include_bytes!("../assets/avatars/hsr/kafka.webp")),
    (
        "lingsha",
        include_bytes!("../assets/avatars/hsr/lingsha.webp"),
    ),
    ("luka", include_bytes!("../assets/avatars/hsr/luka.webp")),
    (
        "luocha",
        include_bytes!("../assets/avatars/hsr/luocha.webp"),
    ),
    ("lynx", include_bytes!("../assets/avatars/hsr/lynx.webp")),
    (
        "march-7th-the-hunt",
        include_bytes!("../assets/avatars/hsr/march-7th-the-hunt.webp"),
    ),
    (
        "march-7th",
        include_bytes!("../assets/avatars/hsr/march-7th.webp"),
    ),
    ("misha", include_bytes!("../assets/avatars/hsr/misha.webp")),
    (
        "mortenax-blade",
        include_bytes!("../assets/avatars/hsr/mortenax-blade.webp"),
    ),
    ("moze", include_bytes!("../assets/avatars/hsr/moze.webp")),
    ("mydei", include_bytes!("../assets/avatars/hsr/mydei.webp")),
    (
        "natasha",
        include_bytes!("../assets/avatars/hsr/natasha.webp"),
    ),
    ("pearl", include_bytes!("../assets/avatars/hsr/pearl.webp")),
    ("pela", include_bytes!("../assets/avatars/hsr/pela.webp")),
    (
        "phainon",
        include_bytes!("../assets/avatars/hsr/phainon.webp"),
    ),
    (
        "qingque",
        include_bytes!("../assets/avatars/hsr/qingque.webp"),
    ),
    ("rappa", include_bytes!("../assets/avatars/hsr/rappa.webp")),
    (
        "rin-tohsaka",
        include_bytes!("../assets/avatars/hsr/rin-tohsaka.webp"),
    ),
    (
        "robin-summeretto",
        include_bytes!("../assets/avatars/hsr/robin-summeretto.webp"),
    ),
    ("robin", include_bytes!("../assets/avatars/hsr/robin.webp")),
    (
        "ruan-mei",
        include_bytes!("../assets/avatars/hsr/ruan-mei.webp"),
    ),
    ("saber", include_bytes!("../assets/avatars/hsr/saber.webp")),
    ("sampo", include_bytes!("../assets/avatars/hsr/sampo.webp")),
    ("seele", include_bytes!("../assets/avatars/hsr/seele.webp")),
    (
        "serval",
        include_bytes!("../assets/avatars/hsr/serval.webp"),
    ),
    (
        "silver-wolf-lv999",
        include_bytes!("../assets/avatars/hsr/silver-wolf-lv999.webp"),
    ),
    (
        "silver-wolf",
        include_bytes!("../assets/avatars/hsr/silver-wolf.webp"),
    ),
    (
        "sparkle",
        include_bytes!("../assets/avatars/hsr/sparkle.webp"),
    ),
    (
        "sparxie",
        include_bytes!("../assets/avatars/hsr/sparxie.webp"),
    ),
    (
        "sunday",
        include_bytes!("../assets/avatars/hsr/sunday.webp"),
    ),
    (
        "sushang",
        include_bytes!("../assets/avatars/hsr/sushang.webp"),
    ),
    (
        "the-dahlia",
        include_bytes!("../assets/avatars/hsr/the-dahlia.webp"),
    ),
    (
        "the-herta",
        include_bytes!("../assets/avatars/hsr/the-herta.webp"),
    ),
    (
        "tingyun",
        include_bytes!("../assets/avatars/hsr/tingyun.webp"),
    ),
    (
        "topaz-and-numby",
        include_bytes!("../assets/avatars/hsr/topaz-and-numby.webp"),
    ),
    (
        "trailblazer-elation",
        include_bytes!("../assets/avatars/hsr/trailblazer-elation.webp"),
    ),
    (
        "trailblazer-remembrance",
        include_bytes!("../assets/avatars/hsr/trailblazer-remembrance.webp"),
    ),
    (
        "trailblazer-the-destruction",
        include_bytes!("../assets/avatars/hsr/trailblazer-the-destruction.webp"),
    ),
    (
        "trailblazer-the-harmony",
        include_bytes!("../assets/avatars/hsr/trailblazer-the-harmony.webp"),
    ),
    (
        "trailblazer-the-preservation",
        include_bytes!("../assets/avatars/hsr/trailblazer-the-preservation.webp"),
    ),
    (
        "tribbie",
        include_bytes!("../assets/avatars/hsr/tribbie.webp"),
    ),
    ("welt", include_bytes!("../assets/avatars/hsr/welt.webp")),
    ("xueyi", include_bytes!("../assets/avatars/hsr/xueyi.webp")),
    (
        "yanqing",
        include_bytes!("../assets/avatars/hsr/yanqing.webp"),
    ),
    (
        "yao-guang",
        include_bytes!("../assets/avatars/hsr/yao-guang.webp"),
    ),
    (
        "yukong",
        include_bytes!("../assets/avatars/hsr/yukong.webp"),
    ),
    ("yunli", include_bytes!("../assets/avatars/hsr/yunli.webp")),
];

static ZZZ_AVATARS: &[BundledAvatar] = &[
    ("alice", include_bytes!("../assets/avatars/zzz/alice.webp")),
    (
        "anby-demara-soldier-0",
        include_bytes!("../assets/avatars/zzz/anby-demara-soldier-0.webp"),
    ),
    (
        "anby-demara",
        include_bytes!("../assets/avatars/zzz/anby-demara.webp"),
    ),
    ("anton", include_bytes!("../assets/avatars/zzz/anton.webp")),
    ("aria", include_bytes!("../assets/avatars/zzz/aria.webp")),
    (
        "astra-yao",
        include_bytes!("../assets/avatars/zzz/astra-yao.webp"),
    ),
    (
        "banyue",
        include_bytes!("../assets/avatars/zzz/banyue.webp"),
    ),
    ("ben", include_bytes!("../assets/avatars/zzz/ben.webp")),
    (
        "billy-kid",
        include_bytes!("../assets/avatars/zzz/billy-kid.webp"),
    ),
    (
        "billy-starlight",
        include_bytes!("../assets/avatars/zzz/billy-starlight.webp"),
    ),
    (
        "burnice",
        include_bytes!("../assets/avatars/zzz/burnice.webp"),
    ),
    (
        "caesar",
        include_bytes!("../assets/avatars/zzz/caesar.webp"),
    ),
    (
        "cissia",
        include_bytes!("../assets/avatars/zzz/cissia.webp"),
    ),
    ("corin", include_bytes!("../assets/avatars/zzz/corin.webp")),
    (
        "dialyn",
        include_bytes!("../assets/avatars/zzz/dialyn.webp"),
    ),
    ("ellen", include_bytes!("../assets/avatars/zzz/ellen.webp")),
    (
        "evelyn",
        include_bytes!("../assets/avatars/zzz/evelyn.webp"),
    ),
    (
        "grace-howard",
        include_bytes!("../assets/avatars/zzz/grace-howard.webp"),
    ),
    (
        "harumasa",
        include_bytes!("../assets/avatars/zzz/harumasa.webp"),
    ),
    ("hugo", include_bytes!("../assets/avatars/zzz/hugo.webp")),
    (
        "jane-doe",
        include_bytes!("../assets/avatars/zzz/jane-doe.webp"),
    ),
    (
        "ju-fufu",
        include_bytes!("../assets/avatars/zzz/ju-fufu.webp"),
    ),
    (
        "koleda",
        include_bytes!("../assets/avatars/zzz/koleda.webp"),
    ),
    (
        "lighter",
        include_bytes!("../assets/avatars/zzz/lighter.webp"),
    ),
    ("lucia", include_bytes!("../assets/avatars/zzz/lucia.webp")),
    ("lucy", include_bytes!("../assets/avatars/zzz/lucy.webp")),
    (
        "lycaon",
        include_bytes!("../assets/avatars/zzz/lycaon.webp"),
    ),
    (
        "manato",
        include_bytes!("../assets/avatars/zzz/manato.webp"),
    ),
    (
        "miyabi",
        include_bytes!("../assets/avatars/zzz/miyabi.webp"),
    ),
    (
        "nangong-yu",
        include_bytes!("../assets/avatars/zzz/nangong-yu.webp"),
    ),
    (
        "nekomata",
        include_bytes!("../assets/avatars/zzz/nekomata.webp"),
    ),
    (
        "nicole-demara",
        include_bytes!("../assets/avatars/zzz/nicole-demara.webp"),
    ),
    ("nom", include_bytes!("../assets/avatars/zzz/nom.webp")),
    ("norma", include_bytes!("../assets/avatars/zzz/norma.webp")),
    (
        "orphie-and-magus",
        include_bytes!("../assets/avatars/zzz/orphie-and-magus.webp"),
    ),
    (
        "pan-yinhu",
        include_bytes!("../assets/avatars/zzz/pan-yinhu.webp"),
    ),
    ("piper", include_bytes!("../assets/avatars/zzz/piper.webp")),
    (
        "promeia",
        include_bytes!("../assets/avatars/zzz/promeia.webp"),
    ),
    (
        "pulchra",
        include_bytes!("../assets/avatars/zzz/pulchra.webp"),
    ),
    (
        "pyrois",
        include_bytes!("../assets/avatars/zzz/pyrois.webp"),
    ),
    (
        "qingyi",
        include_bytes!("../assets/avatars/zzz/qingyi.webp"),
    ),
    (
        "remielle",
        include_bytes!("../assets/avatars/zzz/remiel.webp"),
    ),
    ("rina", include_bytes!("../assets/avatars/zzz/rina.webp")),
    ("seed", include_bytes!("../assets/avatars/zzz/seed.webp")),
    ("seth", include_bytes!("../assets/avatars/zzz/seth.webp")),
    (
        "sigrid",
        include_bytes!("../assets/avatars/zzz/sigrid.webp"),
    ),
    (
        "soldier-11",
        include_bytes!("../assets/avatars/zzz/soldier-11.webp"),
    ),
    (
        "soukaku",
        include_bytes!("../assets/avatars/zzz/soukaku.webp"),
    ),
    ("sunna", include_bytes!("../assets/avatars/zzz/sunna.webp")),
    (
        "trigger",
        include_bytes!("../assets/avatars/zzz/trigger.webp"),
    ),
    (
        "ukinami-yuzuha",
        include_bytes!("../assets/avatars/zzz/ukinami-yuzuha.webp"),
    ),
    (
        "velina",
        include_bytes!("../assets/avatars/zzz/velina.webp"),
    ),
    (
        "vivian",
        include_bytes!("../assets/avatars/zzz/vivian.webp"),
    ),
    (
        "yanagi",
        include_bytes!("../assets/avatars/zzz/yanagi.webp"),
    ),
    (
        "ye-shunguang",
        include_bytes!("../assets/avatars/zzz/ye-shunguang.webp"),
    ),
    (
        "yidhari",
        include_bytes!("../assets/avatars/zzz/yidhari.webp"),
    ),
    (
        "yixuan",
        include_bytes!("../assets/avatars/zzz/yixuan.webp"),
    ),
    ("zhao", include_bytes!("../assets/avatars/zzz/zhao.webp")),
    (
        "zhu-yuan",
        include_bytes!("../assets/avatars/zzz/zhu-yuan.webp"),
    ),
];

pub(crate) fn for_game(game: Game) -> &'static [BundledAvatar] {
    match game {
        Game::Hsr => HSR_AVATARS,
        Game::Zzz => ZZZ_AVATARS,
    }
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeSet;

    use sha2::{Digest, Sha256};

    use super::*;

    #[test]
    fn bundled_avatar_seed_is_complete_unique_and_valid_webp() {
        let manifest: serde_json::Value =
            serde_json::from_str(include_str!("../assets/avatars/manifest-v1.json")).unwrap();
        assert_eq!(
            manifest["schema_version"],
            "miho-bundled-avatar-manifest-v1"
        );
        for (game, game_key, expected) in [(Game::Hsr, "hsr", 93), (Game::Zzz, "zzz", 59)] {
            let avatars = for_game(game);
            assert_eq!(avatars.len(), expected);
            let manifest_rows = manifest["games"][game_key].as_array().unwrap();
            assert_eq!(manifest_rows.len(), expected);
            let mut slugs = BTreeSet::new();
            let mut hashes = BTreeSet::new();
            for ((slug, bytes), row) in avatars.iter().zip(manifest_rows) {
                assert!(slugs.insert(*slug), "duplicate bundled avatar slug {slug}");
                assert!(bytes.len() >= 12);
                assert_eq!(&bytes[..4], b"RIFF");
                assert_eq!(&bytes[8..12], b"WEBP");
                let digest = Sha256::digest(bytes);
                assert!(
                    hashes.insert(digest.to_vec()),
                    "different slugs must not share one avatar payload"
                );
                assert_eq!(row["slug"], *slug);
                assert_eq!(row["bytes"].as_u64(), Some(bytes.len() as u64));
                assert_eq!(row["sha256"], format!("{digest:x}"));
            }
        }
    }
}
