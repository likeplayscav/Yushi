//! tracing 接到 logcat（标签 `qingjian`），panic 也记一条（安卓上 stderr 看不到）；非 Android 目标（本机测试）什么都不做。

#[cfg(target_os = "android")]
pub fn init() {
    use tracing_subscriber::layer::SubscriberExt;
    use tracing_subscriber::util::SubscriberInitExt;

    static ONCE: std::sync::Once = std::sync::Once::new();
    ONCE.call_once(|| {
        if let Ok(layer) = tracing_android::layer("qingjian") {
            // jni crate 每次调用都打 trace，只留 debug 及以上
            let _ = tracing_subscriber::registry()
                .with(tracing_subscriber::filter::LevelFilter::DEBUG)
                .with(layer)
                .try_init();
        }
        // 不记正文、也不接回默认 hook（它会打出正文）：切片越界之类的消息会带上用户打的字
        std::panic::set_hook(Box::new(|info| {
            let location = info.location();
            tracing::error!(
                file = location.map(|location| location.file()),
                line = location.map(|location| location.line()),
                "panic; payload omitted"
            );
        }));
    });
}

#[cfg(not(target_os = "android"))]
pub fn init() {}
