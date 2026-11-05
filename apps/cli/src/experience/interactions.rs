//! 跨输入的体验检查：真实学习器、重新加载、撤回、隐私边界与编辑。

use std::path::Path;

use qingjian_core::{CandidateView, EngineSession};
use qingjian_learning::FrequencyLearner;
use serde_json::{Value, json};

use crate::error::CliError;

fn first(engine: &mut qingjian_core::Engine, keys: &str) -> String {
    engine.set_input(keys);
    engine
        .query()
        .ok()
        .and_then(|q| q.candidates.items.first().map(|c| c.text.clone()))
        .unwrap_or_default()
}

fn select(engine: &mut qingjian_core::Engine, keys: &str, text: &str) -> bool {
    engine.set_input(keys);
    let Some(candidate) = engine
        .query()
        .ok()
        .and_then(|q| q.candidates.items.into_iter().find(|c| c.text == text))
    else {
        return false;
    };
    engine.commit(&candidate) == text
}

pub(super) fn run(folder: &Path) -> Result<Vec<Value>, CliError> {
    // 拒绝复用目录：保证上次测试的学习数据不会污染这次结果。
    std::fs::create_dir(folder)?;
    let mut checks = Vec::new();
    let mut engine = super::engine()?.with_learner(Box::new(FrequencyLearner::from_path(
        folder.join("user.tsv"),
    )?));
    let initial = first(&mut engine, "m");
    let selected = select(&mut engine, "m", "吗");
    engine.break_chain();
    let learned = first(&mut engine, "m");
    checks.push(json!({"id":"same-input-learning", "passed": selected && learned == "吗", "before":initial, "after":learned}));
    engine.flush_learning();
    drop(engine);
    let mut engine = super::engine()?.with_learner(Box::new(FrequencyLearner::from_path(
        folder.join("user.tsv"),
    )?));
    checks.push(json!({"id":"reload-learning", "passed":first(&mut engine,"m") == "吗"}));
    for (id, private) in [("private-input", true), ("learning-disabled", false)] {
        let mut engine = super::engine()?;
        if private {
            engine.set_private(true);
        } else {
            engine.set_learning(false);
        }
        let selected = select(&mut engine, "m", "吗");
        engine.set_private(false);
        engine.set_learning(true);
        checks.push(
            json!({"id":id, "passed":selected && engine.learner().choice_weight("m","吗") == 0}),
        );
    }
    let mut engine = super::engine()?;
    let selected = select(&mut engine, "m", "吗");
    engine.note_backspace();
    let replaced = select(&mut engine, "m", "没");
    checks.push(json!({"id":"replace-wrong-selection", "passed":selected && replaced && engine.learner().choice_weight("m","吗") == 0}));
    let mut engine = super::engine()?;
    engine.set_input("database");
    checks.push(json!({"id":"raw-enter", "passed":engine.take_raw() == "database" && engine.composition().is_empty()}));
    engine.set_input("nihaoa");
    engine.backspace();
    let edited = engine.composition().text() == "nihao";
    checks.push(
        json!({"id":"backspace-edit", "passed":edited && first(&mut engine,"nihao") == "你好"}),
    );
    engine.set_input("zhangwei");
    engine.set_candidate_view(CandidateView::Characters);
    let mut other = EngineSession::default();
    engine.swap_session(&mut other);
    let isolated =
        engine.composition().is_empty() && engine.candidate_view() == CandidateView::Compact;
    engine.set_input("nihao");
    engine.swap_session(&mut other);
    checks.push(json!({"id":"switch-input-box", "passed":isolated && engine.composition().text() == "zhangwei"}));
    engine.discard_input();
    checks.push(json!({"id":"discard-private-composition", "passed":engine.composition().is_empty() && engine.candidate_view() == CandidateView::Compact}));
    std::fs::remove_dir_all(folder)?;
    Ok(checks)
}
