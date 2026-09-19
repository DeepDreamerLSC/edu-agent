"""外部数据 importer 包(#368):每个 importer 只做 upstream → v1,到此为止。

禁区:不做 mapping DSL / 插件框架 / 自动猜测 HF dataset——四个 Python adapter
比任何通用框架可靠。首 importer(SocraticMATH)验证 schema 成立即止,其余三套
(MathDial/MathTutorBench/MMTutorBench)不在本单。
"""
