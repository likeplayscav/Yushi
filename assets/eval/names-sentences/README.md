# 姓名与日常语句抽测

80 条人工选择、人工标音的固定样例：24 个常见姓氏的人名写法、16 个公共人物名、32 条原创日常短句、8 条含姓名的原创句子。不是人口姓名频率排行榜，也不代表全体姓名覆盖率。姓名同音存在多个正确写法，这里衡量目标写法的候选可达性与排名，不将其他姓名断言为错字。

每条生成全拼、尾音节只输首字母、全简拼、交错简拼，重复按键串只计算一次。种子在首次查询前冻结，不按结果改答案，不补入产品词库。所有失败保留，分组报告 Top-1 / Top-3 / Top-5、解析失败和字符错误。

```bash
python3 tools/eval/names_sentences.py --binary target/release/qingjian-cli --output target/names-static
python3 tools/eval/names_sentences.py --binary target/release/qingjian-cli --output target/names-model --model data/models/hanzhang-tongbian/hanzhang-tongbian-small.qjm
```

默认测本地拼音候选，不读取个人学习数据、不发云端请求；可选模型为含章·通变 P2C。简拼和末音节未完成衡量输入补全，不等同于上屏后无拼音的下一句续写。`reference.json` 固定本轮 Linux 实测的首选与目标排名，Windows 原生构建用 `--reference` 检查逐条 Top-1 / Top-5 无回退；命中率不足会如实记录，不冒充全部姓名都正确。
