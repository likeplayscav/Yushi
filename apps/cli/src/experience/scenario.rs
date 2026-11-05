//! 冻结的打字任务；目标只用于模拟选词，不参与词库或模型装配。

use serde::Deserialize;

#[derive(Deserialize)]
pub(super) struct Scenario {
    pub id: String,

    pub scene: String,

    pub text: String,

    pub keys: String,

    #[serde(default)]
    pub erase: usize,

    #[serde(default)]
    pub english: bool,

    #[serde(default)]
    pub punctuation: Option<char>,
}
