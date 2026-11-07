# Alternate Workflow Extension · Minimal Review Pack

> E6 test extension: deliberately smaller than the default catalog. It is a replaceable method pack, not a new Core.

## Seed ALT-REVIEW · Risk-triggered independent review

- 适用场景：语义解析、边界、别名、不可变性或隐藏契约风险。
- 步骤骨架：inspect → patch → public_check → review → revise → public_check → submit。
- 选择信号：公开检查不足以证明边界或副作用安全。
- 改造规则：只在 review 给出具体风险时 revise；返修后必须再次 public_check。
- 失败模式：没有真实 review 回执、无风险强行返修、返修后不复测。
